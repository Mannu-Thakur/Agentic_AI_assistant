import { useState, useEffect } from 'react';
import { useUIStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { useChatStore } from '../store/chatStore';
import {
  Sun, Moon, User, Sliders, Key,
  Brain, Zap, Save, Eye, EyeOff,
  Check, Trash2, LogOut, Cpu, AlertCircle, Shield, Loader2, Palette,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../services/api';

type SettingsTab = 'models' | 'generation' | 'features' | 'appearance' | 'account';

const TABS: { id: SettingsTab; label: string; icon: React.ElementType }[] = [
  { id: 'models',     label: 'AI Models',   icon: Cpu     },
  { id: 'generation', label: 'Generation',  icon: Zap     },
  { id: 'features',   label: 'AI Features', icon: Brain   },
  { id: 'appearance', label: 'Appearance',  icon: Sliders },
  { id: 'account',    label: 'Account',     icon: User    },
];

const MODEL_OPTIONS = [
  { id: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash', provider: 'Google' },
  { id: 'gemini-1.5-pro',   label: 'Gemini 1.5 Pro',   provider: 'Google' },
  { id: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B',   provider: 'Groq' },
  { id: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B', provider: 'Groq' },
];

// ─── Utility: masked key input ───────────────────────────────
function ApiKeyField({
  label,
  provider,
  initialMaskedKey,
  onSaveSuccess,
  onDeleteSuccess,
}: {
  label: string;
  provider: string;
  initialMaskedKey: string;
  onSaveSuccess: (maskedKey: string) => void;
  onDeleteSuccess: () => void;
}) {
  const [val, setVal]       = useState(initialMaskedKey);
  const [show, setShow]     = useState(false);
  const [statusState, setStatusState] = useState<'idle' | 'verifying' | 'verified' | 'error'>(
    initialMaskedKey ? 'verified' : 'idle'
  );
  const [errorMsg, setErrorMsg] = useState('');

  // Update state when initialMaskedKey changes
  useEffect(() => {
    setVal(initialMaskedKey);
    setStatusState(initialMaskedKey ? 'verified' : 'idle');
    setErrorMsg('');
  }, [initialMaskedKey]);

  const handleSave = async () => {
    if (!val.trim()) return;
    setStatusState('verifying');
    setErrorMsg('');
    try {
      const res = await apiRequest('/api-keys', {
        method: 'POST',
        json: {
          provider_name: provider,
          api_key: val
        }
      });
      setVal(res.masked_key);
      setStatusState('verified');
      onSaveSuccess(res.masked_key);
    } catch (err: any) {
      setStatusState('error');
      setErrorMsg(err.message || 'Verification failed. Check that your key is valid and has the required permissions.');
    }
  };

  const handleDelete = async () => {
    try {
      await apiRequest(`/api-keys/${provider}`, {
        method: 'DELETE'
      });
      setVal('');
      setStatusState('idle');
      setErrorMsg('');
      onDeleteSuccess();
    } catch (err: any) {
      console.error('Delete failed:', err);
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label className="text-xs font-semibold text-foreground-2 flex items-center gap-1.5">
          <Key className="w-3 h-3 text-foreground-3" />
          {label}
        </label>
        <div className="flex items-center gap-1.5">
          {statusState === 'verifying' && (
            <span className="text-[10px] text-accent font-normal flex items-center gap-1">
              <Loader2 className="w-2.5 h-2.5 animate-spin" /> Verifying...
            </span>
          )}
          {statusState === 'verified' && (
            <span className="text-[10px] text-green-400 font-normal flex items-center gap-1">
              <Check className="w-2.5 h-2.5" /> Verified & Saved
            </span>
          )}
          {statusState === 'error' && (
            <span className="text-[10px] text-red-400 font-normal flex items-center gap-1">
              <AlertCircle className="w-2.5 h-2.5" /> Failed
            </span>
          )}
        </div>
      </div>
      <div className="flex gap-1.5">
        <div className="relative flex-1">
          <input
            type={show ? 'text' : 'password'}
            value={val}
            onChange={(e) => setVal(e.target.value)}
            placeholder={initialMaskedKey ? '••••••••••••••••' : `Enter ${label}...`}
            className="w-full bg-surface-2 border border-border rounded-lg px-3 py-2 pr-9 text-xs font-mono text-foreground placeholder:text-foreground-3 focus:outline-none focus:border-accent transition-colors"
          />
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-foreground-3 hover:text-foreground transition-colors"
          >
            {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          </button>
        </div>
        <button
          onClick={handleSave}
          disabled={statusState === 'verifying' || !val.trim()}
          className={`px-3 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 flex-shrink-0 border
            ${statusState === 'verified'
              ? 'bg-green-500/10 border-green-500/30 text-green-400'
              : statusState === 'error'
              ? 'bg-red-500/10 border-red-500/30 text-red-400 hover:bg-red-500/20'
              : statusState === 'verifying'
              ? 'bg-surface-2 border-border text-foreground-3 cursor-not-allowed'
              : 'bg-accent/10 border-accent/30 text-accent hover:bg-accent/20'}`}
        >
          {statusState === 'verifying'
            ? <Loader2 className="w-3 h-3 animate-spin" />
            : statusState === 'verified'
            ? <Check className="w-3 h-3" />
            : <Save className="w-3 h-3" />
          }
          {statusState === 'verifying' ? 'Verifying' : statusState === 'verified' ? 'Saved' : 'Verify & Save'}
        </button>
        {initialMaskedKey && (
          <button
            onClick={handleDelete}
            className="px-2.5 rounded-lg text-xs font-semibold border border-red-500/30 bg-red-500/5 hover:bg-red-500/15 text-red-400 flex items-center justify-center flex-shrink-0 transition-colors"
            title="Remove key"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      {errorMsg && (
        <p className="text-[10px] text-red-400 leading-normal mt-1 bg-red-500/5 border border-red-500/10 p-2.5 rounded-lg">
          {errorMsg}
        </p>
      )}
    </div>
  );
}

// ─── Toggle switch ────────────────────────────────────────────
function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative w-10 h-5 rounded-full transition-colors flex items-center px-0.5
        ${checked ? 'bg-accent' : 'bg-surface-3'}`}
    >
      <span className={`w-4 h-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
    </button>
  );
}

// ─── Setting row ──────────────────────────────────────────────
function SettingRow({
  label, desc, children, danger,
}: { label: string; desc?: string; children: React.ReactNode; danger?: boolean }) {
  return (
    <div className={`flex items-center justify-between py-3.5 border-b border-border last:border-0 gap-4
      ${danger ? 'text-red-400' : ''}`}>
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        {desc && <p className="text-[11px] text-foreground-3 mt-0.5 leading-relaxed">{desc}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

// ─── Section card ─────────────────────────────────────────────
function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-surface overflow-hidden">
      <div className="px-4 py-3 bg-surface-2 border-b border-border">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground-3">{title}</h3>
      </div>
      <div className="px-4 divide-y divide-border">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const { theme, setTheme, developerMode, toggleDeveloperMode } = useUIStore();
  const { user, logout } = useAuthStore();
  const { activeModel, setActiveModel, setChats, setActiveChatId, setMessages } = useChatStore();
  const navigate = useNavigate();

  const [tab, setTab] = useState<SettingsTab>('models');

  // Generation settings (local storage)
  const [temperature, setTemperature] = useState<number>(() => parseFloat(localStorage.getItem('llm_temperature') || '0.7'));
  const [maxTokens, setMaxTokens]     = useState<number>(() => parseInt(localStorage.getItem('llm_max_tokens') || '2048', 10));
  const [streaming, setStreaming]     = useState<boolean>(() => localStorage.getItem('llm_streaming') !== 'false');
  const [memoryEnabled, setMemory]    = useState<boolean>(() => localStorage.getItem('feature_memory') !== 'false');
  const [ragEnabled, setRag]          = useState<boolean>(() => localStorage.getItem('feature_rag') !== 'false');
  const [toolsEnabled, setTools]      = useState<boolean>(() => localStorage.getItem('feature_tools') !== 'false');
  const [webEnabled, setWeb]          = useState<boolean>(() => localStorage.getItem('feature_web') !== 'false');
  const [saved, setSaved]             = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  // Dynamic API Keys state
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({
    gemini: '',
    groq: '',
    openrouter: '',
  });
  const [loadingKeys, setLoadingKeys] = useState(true);

  const handleSaveGeneration = () => {
    localStorage.setItem('llm_temperature', String(temperature));
    localStorage.setItem('llm_max_tokens',  String(maxTokens));
    localStorage.setItem('llm_streaming',   String(streaming));
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const handleDeleteConversations = async () => {
    if (!deleteConfirm) { setDeleteConfirm(true); return; }
    try {
      await apiRequest('/chats/all', { method: 'DELETE' });
    } catch {/* ignore */ }
    setChats([]);
    setActiveChatId(null);
    setMessages([]);
    setDeleteConfirm(false);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Save feature flags immediately
  useEffect(() => { localStorage.setItem('feature_memory', String(memoryEnabled)); }, [memoryEnabled]);
  useEffect(() => { localStorage.setItem('feature_rag',    String(ragEnabled));    }, [ragEnabled]);
  useEffect(() => { localStorage.setItem('feature_tools',  String(toolsEnabled));  }, [toolsEnabled]);
  useEffect(() => { localStorage.setItem('feature_web',    String(webEnabled));    }, [webEnabled]);

  // Load API keys configuration from DB on mount
  useEffect(() => {
    async function fetchKeys() {
      try {
        const keys = await apiRequest('/api-keys');
        const keyMap: Record<string, string> = { gemini: '', groq: '', openrouter: '' };
        for (const k of keys) {
          keyMap[k.provider_name] = k.masked_key;
        }
        setApiKeys(keyMap);
      } catch (err) {
        console.error('Failed to fetch API keys:', err);
      } finally {
        setLoadingKeys(false);
      }
    }
    fetchKeys();
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">

        {/* Header */}
        <div>
          <h1 className="text-xl font-semibold text-foreground tracking-tight">Settings</h1>
          <p className="text-foreground-3 text-xs mt-1">Configure your workspace and AI preferences</p>
        </div>

        <div className="flex gap-6">

          {/* Sidebar tabs */}
          <aside className="w-44 flex-shrink-0 space-y-0.5">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-all
                  ${tab === id
                    ? 'bg-accent/10 text-accent border border-accent/20'
                    : 'text-foreground-2 hover:text-foreground hover:bg-surface-2'}`}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </aside>

          {/* Main panel */}
          <div className="flex-1 space-y-4 min-w-0">

            {/* ── AI Models tab ── */}
            {tab === 'models' && (
              <>
                <SectionCard title="API Keys">
                  <div className="py-4 space-y-4">
                    {loadingKeys ? (
                      <div className="text-xs text-foreground-3 animate-pulse py-2 text-center">Loading keys configuration...</div>
                    ) : (
                      <>
                        <ApiKeyField
                          label="Google Gemini API Key"
                          provider="gemini"
                          initialMaskedKey={apiKeys.gemini}
                          onSaveSuccess={(key) => setApiKeys((prev) => ({ ...prev, gemini: key }))}
                          onDeleteSuccess={() => setApiKeys((prev) => ({ ...prev, gemini: '' }))}
                        />
                        <ApiKeyField
                          label="Groq API Key"
                          provider="groq"
                          initialMaskedKey={apiKeys.groq}
                          onSaveSuccess={(key) => setApiKeys((prev) => ({ ...prev, groq: key }))}
                          onDeleteSuccess={() => setApiKeys((prev) => ({ ...prev, groq: '' }))}
                        />
                        <ApiKeyField
                          label="OpenRouter API Key"
                          provider="openrouter"
                          initialMaskedKey={apiKeys.openrouter}
                          onSaveSuccess={(key) => setApiKeys((prev) => ({ ...prev, openrouter: key }))}
                          onDeleteSuccess={() => setApiKeys((prev) => ({ ...prev, openrouter: '' }))}
                        />
                      </>
                    )}
                  </div>
                </SectionCard>

                <SectionCard title="Default Model">
                  <div className="py-3">
                    <div className="grid grid-cols-2 gap-2">
                      {MODEL_OPTIONS.map((m) => (
                        <button
                          key={m.id}
                          onClick={() => setActiveModel(m.id)}
                          className={`p-3 rounded-lg border text-left transition-all
                            ${activeModel === m.id
                              ? 'border-accent/40 bg-accent/10 text-foreground'
                              : 'border-border bg-surface-2 text-foreground-2 hover:bg-surface-3 hover:text-foreground'}`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-semibold">{m.label}</span>
                            {activeModel === m.id && <Check className="w-3 h-3 text-accent" />}
                          </div>
                          <span className="text-[10px] text-foreground-3">{m.provider}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </SectionCard>

                <div className="flex items-start gap-2 p-3 rounded-lg border border-accent/15 bg-accent/5 text-[11px] text-foreground-2">
                  <Shield className="w-3.5 h-3.5 text-accent mt-0.5 flex-shrink-0" />
                  <span>Keys are verified against the provider API before storage. They are <strong>AES-encrypted</strong> at rest in the database and never exposed in logs or API responses — only masked previews are returned.</span>
                </div>
              </>
            )}

            {/* ── Generation tab ── */}
            {tab === 'generation' && (
              <SectionCard title="Generation Parameters">
                <SettingRow
                  label="Temperature"
                  desc={`Controls randomness. Lower = more focused, higher = more creative. Current: ${temperature}`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-foreground-3 w-5 text-right">0</span>
                    <input
                      type="range" min="0" max="1" step="0.05"
                      value={temperature}
                      onChange={(e) => setTemperature(parseFloat(e.target.value))}
                      className="w-28 accent-accent h-1.5 rounded appearance-none cursor-pointer"
                    />
                    <span className="text-xs text-foreground-3 w-5">1</span>
                    <span className="text-xs font-mono font-semibold text-foreground w-8 text-right">{temperature}</span>
                  </div>
                </SettingRow>

                <SettingRow
                  label="Max Output Tokens"
                  desc="Maximum number of tokens in the response."
                >
                  <input
                    type="number"
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(Math.max(256, Math.min(8192, parseInt(e.target.value) || 2048)))}
                    min={256} max={8192} step={256}
                    className="w-24 bg-surface-2 border border-border rounded-lg px-2 py-1.5 text-xs text-foreground text-right focus:outline-none focus:border-accent transition-colors"
                  />
                </SettingRow>

                <SettingRow label="Streaming Responses" desc="Show responses as they are generated token by token.">
                  <Toggle checked={streaming} onChange={setStreaming} />
                </SettingRow>

                <div className="py-3 flex justify-end">
                  <button
                    onClick={handleSaveGeneration}
                    className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold transition-all border
                      ${saved
                        ? 'bg-green-500/10 border-green-500/30 text-green-400'
                        : 'bg-accent/10 border-accent/30 text-accent hover:bg-accent/20'}`}
                  >
                    {saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
                    {saved ? 'Saved!' : 'Save Changes'}
                  </button>
                </div>
              </SectionCard>
            )}

            {/* ── Features tab ── */}
            {tab === 'features' && (
              <SectionCard title="AI Feature Flags">
                <SettingRow label="Semantic Memory" desc="Automatically extract and recall long-term facts about you.">
                  <Toggle checked={memoryEnabled} onChange={setMemory} />
                </SettingRow>
                <SettingRow label="RAG (Document Q&A)" desc="Use uploaded documents as context for responses.">
                  <Toggle checked={ragEnabled} onChange={setRag} />
                </SettingRow>
                <SettingRow label="Tool Calling" desc="Allow the AI to execute functions and external tools.">
                  <Toggle checked={toolsEnabled} onChange={setTools} />
                </SettingRow>
                <SettingRow label="Web Search" desc="Enable real-time web search via Tavily.">
                  <Toggle checked={webEnabled} onChange={setWeb} />
                </SettingRow>
                <SettingRow label="Developer HUD" desc="Show execution telemetry alongside chat messages.">
                  <Toggle checked={developerMode} onChange={(v) => { if (v !== developerMode) toggleDeveloperMode(); }} />
                </SettingRow>
              </SectionCard>
            )}

            {/* ── Appearance tab ── */}
            {tab === 'appearance' && (
              <SectionCard title="Interface">
                <SettingRow label="Color Theme" desc="Choose how the interface looks. Changes apply instantly.">
                  <div className="flex gap-1.5">
                    {([
                      { value: 'dark',       label: 'Dark',       icon: Moon,    bg: '#0d0e11', fg: '#e6e6ea', accent: '#5B5BD6' },
                      { value: 'light-dark', label: 'Light Dark', icon: Palette, bg: '#191A20', fg: '#f1f1f3', accent: '#6C6EE8' },
                      { value: 'light',      label: 'Light',      icon: Sun,     bg: '#fafafa', fg: '#161618', accent: '#4A4AC4' },
                    ] as const).map(({ value, label, icon: Icon, bg, fg, accent }) => (
                      <button
                        key={value}
                        onClick={() => setTheme(value)}
                        title={label}
                        className={`flex flex-col items-center gap-1.5 px-3 py-2.5 rounded-xl border transition-all
                          ${theme === value
                            ? 'border-accent bg-accent/10 ring-1 ring-accent/30'
                            : 'border-border bg-surface-2 hover:bg-surface-3 hover:border-border-2'}`}
                      >
                        {/* Mini preview swatch */}
                        <div
                          className="w-10 h-7 rounded-lg overflow-hidden border border-border/50 flex flex-col"
                          style={{ background: bg }}
                        >
                          <div className="h-2 flex items-center px-1 gap-0.5" style={{ background: bg }}>
                            <div className="w-1.5 h-1.5 rounded-full" style={{ background: accent }} />
                            <div className="flex-1 h-0.5 rounded-full" style={{ background: fg, opacity: 0.3 }} />
                          </div>
                          <div className="flex-1 flex items-center justify-center gap-0.5 px-0.5">
                            <div className="w-2 h-3 rounded-sm" style={{ background: fg, opacity: 0.08 }} />
                            <div className="flex-1 space-y-0.5">
                              <div className="h-0.5 rounded-full" style={{ background: fg, opacity: 0.4 }} />
                              <div className="h-0.5 rounded-full w-3/4" style={{ background: fg, opacity: 0.25 }} />
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <Icon className={`w-3 h-3 ${theme === value ? 'text-accent' : 'text-foreground-3'}`} />
                          <span className={`text-[10px] font-semibold ${theme === value ? 'text-accent' : 'text-foreground-2'}`}>{label}</span>
                        </div>
                        {theme === value && <Check className="w-2.5 h-2.5 text-accent" />}
                      </button>
                    ))}
                  </div>
                </SettingRow>
              </SectionCard>
            )}

            {/* ── Account tab ── */}
            {tab === 'account' && (
              <>
                <SectionCard title="Profile">
                  <SettingRow label="Name" desc={user?.full_name || 'Not set'}>
                    <span className="text-xs text-foreground-3">{user?.email}</span>
                  </SettingRow>
                </SectionCard>

                <SectionCard title="Data">
                  <SettingRow label="Delete All Conversations" desc="Permanently remove all chat history." danger>
                    <button
                      onClick={handleDeleteConversations}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all
                        ${deleteConfirm
                          ? 'bg-red-500/15 border-red-500/40 text-red-400 hover:bg-red-500/25'
                          : 'bg-surface-2 border-border text-red-400/80 hover:text-red-400 hover:bg-red-500/10'}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      {deleteConfirm ? 'Confirm Delete' : 'Delete All'}
                    </button>
                  </SettingRow>
                </SectionCard>

                <SectionCard title="Session">
                  <SettingRow label="Sign Out" desc="Log out of your current workspace session." danger>
                    <button
                      onClick={handleLogout}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/5 hover:bg-red-500/15 text-red-400 text-xs font-semibold transition-all"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      Logout
                    </button>
                  </SettingRow>
                </SectionCard>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
