/**
 * ArtifactBrowser.tsx — Workspace Artifact Browser
 *
 * Full-featured artifact management panel showing all files produced
 * by agents across sessions — with type filtering, search, preview,
 * and download. Connects to /api/v1/artifacts/* endpoints.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  FileText, Code2, Globe, BarChart2, Download, Trash2,
  RefreshCw, Search, X, Eye, Loader2,
  File, ChevronDown, ChevronUp,
  Cpu, Shield, Presentation
} from 'lucide-react';
import { BASE_URL } from '../../services/api';
import { useAuthStore } from '../../store/authStore';

// ─────────────────────────────────────────────────────────────
//  Types
// ─────────────────────────────────────────────────────────────

interface Artifact {
  id: string;
  type: string;
  filename: string;
  size_bytes: number;
  description: string;
  agent: string;
  user_id: string;
  session_id: string;
  created_at: string;
  download_url: string;
  preview?: string;
  mime_type: string;
}

// ─────────────────────────────────────────────────────────────
//  Icon + colour helpers
// ─────────────────────────────────────────────────────────────

const TYPE_CONFIG: Record<string, { icon: React.ElementType; label: string; color: string; bg: string }> = {
  code:     { icon: Code2,         label: 'Code',         color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
  report:   { icon: FileText,      label: 'Report',       color: 'text-blue-400',    bg: 'bg-blue-500/10' },
  pptx:     { icon: Presentation,  label: 'Presentation', color: 'text-orange-400',  bg: 'bg-orange-500/10' },
  docx:     { icon: FileText,      label: 'Document',     color: 'text-indigo-400',  bg: 'bg-indigo-500/10' },
  csv:      { icon: BarChart2,     label: 'Data',         color: 'text-purple-400',  bg: 'bg-purple-500/10' },
  image:    { icon: Globe,         label: 'Image',        color: 'text-rose-400',    bg: 'bg-rose-500/10' },
  pdf:      { icon: FileText,      label: 'PDF',          color: 'text-red-400',     bg: 'bg-red-500/10' },
  default:  { icon: File,          label: 'File',         color: 'text-gray-400',    bg: 'bg-gray-500/10' },
};

const AGENT_CONFIG: Record<string, { color: string; icon: React.ElementType }> = {
  code:          { color: 'text-emerald-400', icon: Code2 },
  web_research:  { color: 'text-blue-400',    icon: Globe },
  document:      { color: 'text-orange-400',  icon: FileText },
  data_analysis: { color: 'text-purple-400',  icon: BarChart2 },
  rag:           { color: 'text-amber-400',   icon: FileText },
  vision:        { color: 'text-rose-400',    icon: Eye },
  critic:        { color: 'text-red-400',     icon: Shield },
};

function getTypeConfig(type: string) {
  return TYPE_CONFIG[type] || TYPE_CONFIG.default;
}

function formatSize(bytes: number): string {
  if (bytes < 1024)       return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  } catch {
    return iso;
  }
}

// ─────────────────────────────────────────────────────────────
//  API helpers
// ─────────────────────────────────────────────────────────────

async function fetchArtifacts(token: string): Promise<Artifact[]> {
  const res = await fetch(`${BASE_URL}/api/v1/artifacts`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.artifacts || [];
}

async function deleteArtifact(id: string, token: string): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/api/v1/artifacts/${id}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` },
  });
  return res.ok || res.status === 204;
}

// ─────────────────────────────────────────────────────────────
//  Preview Modal
// ─────────────────────────────────────────────────────────────

function PreviewModal({ artifact, onClose }: { artifact: Artifact; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border rounded-2xl p-5 max-w-2xl w-full mx-4 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {(() => { const cfg = getTypeConfig(artifact.type); const Icon = cfg.icon; return <Icon className={`w-4 h-4 ${cfg.color}`} />; })()}
            <span className="font-semibold text-sm text-foreground">{artifact.filename}</span>
          </div>
          <button onClick={onClose} className="text-foreground-3 hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="bg-surface-2 rounded-xl p-4 font-mono text-xs max-h-80 overflow-y-auto whitespace-pre-wrap text-foreground-2 border border-border">
          {artifact.preview || '(No preview available)'}
        </div>
        <div className="flex gap-2 mt-4">
          <a
            href={`${BASE_URL}${artifact.download_url}`}
            download={artifact.filename}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Download
          </a>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Artifact Card
// ─────────────────────────────────────────────────────────────

function ArtifactCard({
  artifact,
  onDelete,
  onPreview,
}: {
  artifact: Artifact;
  onDelete: () => void;
  onPreview: () => void;
}) {
  const cfg      = getTypeConfig(artifact.type);
  const agentCfg = AGENT_CONFIG[artifact.agent] || { color: 'text-gray-400', icon: Cpu };
  const AgentIcon = agentCfg.icon;
  const TypeIcon  = cfg.icon;

  return (
    <div className="group flex items-start gap-3 p-3 rounded-xl border border-border bg-card hover:bg-surface-1 transition-all">
      {/* Type icon */}
      <div className={`flex-shrink-0 p-2.5 rounded-xl ${cfg.bg} border border-border`}>
        <TypeIcon className={`w-4 h-4 ${cfg.color}`} />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="font-medium text-sm text-foreground truncate" title={artifact.filename}>
            {artifact.filename}
          </p>
          <span className="flex-shrink-0 text-[10px] text-foreground-3 font-mono">
            {formatSize(artifact.size_bytes)}
          </span>
        </div>
        {artifact.description && (
          <p className="text-[11px] text-foreground-3 mt-0.5 truncate">{artifact.description}</p>
        )}
        <div className="flex items-center gap-2 mt-1.5">
          <div className="flex items-center gap-1">
            <AgentIcon className={`w-2.5 h-2.5 ${agentCfg.color}`} />
            <span className="text-[10px] text-foreground-3 capitalize">
              {artifact.agent.replace(/_/g, ' ')}
            </span>
          </div>
          <span className="text-[10px] text-foreground-3">•</span>
          <span className="text-[10px] text-foreground-3">{formatDate(artifact.created_at)}</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {artifact.preview && (
          <button
            onClick={onPreview}
            className="p-1.5 rounded-lg hover:bg-surface-2 text-foreground-3 hover:text-foreground transition-colors"
            title="Preview"
          >
            <Eye className="w-3.5 h-3.5" />
          </button>
        )}
        <a
          href={`${BASE_URL}${artifact.download_url}`}
          download={artifact.filename}
          className="p-1.5 rounded-lg hover:bg-surface-2 text-foreground-3 hover:text-foreground transition-colors"
          title="Download"
        >
          <Download className="w-3.5 h-3.5" />
        </a>
        <button
          onClick={onDelete}
          className="p-1.5 rounded-lg hover:bg-red-500/10 text-foreground-3 hover:text-red-400 transition-colors"
          title="Delete"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Main Component
// ─────────────────────────────────────────────────────────────

export function ArtifactBrowser() {
  const { token } = useAuthStore();
  const [artifacts, setArtifacts]       = useState<Artifact[]>([]);
  const [loading, setLoading]           = useState(false);
  const [search, setSearch]             = useState('');
  const [typeFilter, setTypeFilter]     = useState<string>('all');
  const [agentFilter, setAgentFilter]   = useState<string>('all');
  const [previewArt, setPreviewArt]     = useState<Artifact | null>(null);
  const [collapsed, setCollapsed]       = useState(false);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const arts = await fetchArtifacts(token);
      setArtifacts(arts);
    } catch (e) {
      console.error('Failed to load artifacts:', e);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = useCallback(async (id: string) => {
    if (!token) return;
    const ok = await deleteArtifact(id, token);
    if (ok) setArtifacts(prev => prev.filter(a => a.id !== id));
  }, [token]);

  // Derived values
  const allTypes  = ['all', ...Array.from(new Set(artifacts.map(a => a.type)))];
  const allAgents = ['all', ...Array.from(new Set(artifacts.map(a => a.agent)))];

  const filtered = artifacts.filter(a => {
    const matchType  = typeFilter  === 'all' || a.type  === typeFilter;
    const matchAgent = agentFilter === 'all' || a.agent === agentFilter;
    const matchSearch = !search || (
      a.filename.toLowerCase().includes(search.toLowerCase()) ||
      a.description?.toLowerCase().includes(search.toLowerCase())
    );
    return matchType && matchAgent && matchSearch;
  });

  // Stats
  const totalSize = artifacts.reduce((s, a) => s + a.size_bytes, 0);

  return (
    <div className="border border-border rounded-2xl bg-card/50 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-3 border-b border-border/60 cursor-pointer hover:bg-surface-1 transition-colors"
        onClick={() => setCollapsed(p => !p)}
      >
        <File className="w-4 h-4 text-accent" />
        <span className="font-semibold text-sm text-foreground">Workspace Artifacts</span>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent/15 text-accent border border-accent/20 font-medium">
          {artifacts.length} files
        </span>
        <span className="text-[10px] text-foreground-3">{formatSize(totalSize)}</span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={e => { e.stopPropagation(); load(); }}
            className="p-1 rounded-lg hover:bg-surface-2 text-foreground-3 hover:text-foreground transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {collapsed
            ? <ChevronDown className="w-3.5 h-3.5 text-foreground-3" />
            : <ChevronUp   className="w-3.5 h-3.5 text-foreground-3" />}
        </div>
      </div>

      {!collapsed && (
        <div className="p-3 space-y-3">
          {/* Filters */}
          <div className="flex gap-2 flex-wrap">
            {/* Search */}
            <div className="flex-1 min-w-[160px] relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-3" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search artifacts..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-border bg-surface-2 text-xs text-foreground placeholder:text-foreground-3 focus:outline-none focus:border-accent/50"
              />
              {search && (
                <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-foreground-3 hover:text-foreground">
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>

            {/* Type filter */}
            <select
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value)}
              className="px-2 py-1.5 rounded-lg border border-border bg-surface-2 text-xs text-foreground focus:outline-none focus:border-accent/50"
            >
              {allTypes.map(t => (
                <option key={t} value={t}>{t === 'all' ? 'All types' : t}</option>
              ))}
            </select>

            {/* Agent filter */}
            <select
              value={agentFilter}
              onChange={e => setAgentFilter(e.target.value)}
              className="px-2 py-1.5 rounded-lg border border-border bg-surface-2 text-xs text-foreground focus:outline-none focus:border-accent/50"
            >
              {allAgents.map(a => (
                <option key={a} value={a}>{a === 'all' ? 'All agents' : a.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>

          {/* Content */}
          {loading ? (
            <div className="flex items-center justify-center py-8 gap-2 text-foreground-3">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-xs">Loading artifacts...</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-8 text-foreground-3 text-xs">
              {artifacts.length === 0
                ? 'No artifacts yet. Run a mission to generate files.'
                : 'No artifacts match your filters.'}
            </div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {filtered.map(art => (
                <ArtifactCard
                  key={art.id}
                  artifact={art}
                  onDelete={() => handleDelete(art.id)}
                  onPreview={() => setPreviewArt(art)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Preview modal */}
      {previewArt && (
        <PreviewModal artifact={previewArt} onClose={() => setPreviewArt(null)} />
      )}
    </div>
  );
}

export default ArtifactBrowser;
