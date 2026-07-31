import { useState, useEffect, useRef, useCallback, memo, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useUIStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { useChatStore, Provider } from '../store/chatStore';
import { Tooltip } from '../components/ui/Tooltip';
import { CustomSelect, SelectOption } from '../components/ui/CustomSelect';
import { ToastContainer } from '../components/ui/Toast';
import { useToast } from '../hooks/useToast';
import {
  User, Sliders, Key,
  Brain, Zap, Save, Eye, EyeOff,
  Check, Trash2, LogOut, Cpu, AlertCircle, Shield, Loader2, Download,
  RefreshCw, ArrowLeft, FolderClosed, UploadCloud, CheckCircle2,
  XCircle, FileText, FileCode, Sparkles, Calendar, Info, ChevronRight,
  Database, Layers, Scissors, HardDrive, Plus, Monitor,
  Sun, Moon, Globe, Type, Archive, Link2, RotateCcw
} from 'lucide-react';
import { apiRequest } from '../services/api';
import { ProviderKeyManager } from '../services/providerKeyManager';

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Types & Constants
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

type SettingsTab = 'general' | 'datacontrols' | 'models' | 'generation' | 'features' | 'mcpservers' | 'documents' | 'memories' | 'account';

const TABS: { id: SettingsTab | 'chat'; label: string; icon: React.ElementType }[] = [
  { id: 'chat',       label: 'Back to Chat',    icon: ArrowLeft   },
  { id: 'general',    label: 'General',         icon: Sliders     },
  { id: 'datacontrols', label: 'Data controls', icon: Database    },
  { id: 'models',     label: 'AI Models',       icon: Cpu         },
  { id: 'generation', label: 'Generation',      icon: Zap         },
  { id: 'features',   label: 'AI Features',     icon: Brain       },
  { id: 'mcpservers', label: 'Remote MCP Servers', icon: Link2    },
  { id: 'documents',  label: 'Documents',       icon: FolderClosed},
  { id: 'memories',   label: 'Semantic Memory', icon: Sparkles    },
  { id: 'account',    label: 'Account & Security', icon: User     },
];


const PROVIDER_METADATA: Record<string, { name: string; label: string; placeholder: string; desc: string }> = {
  alibaba:    { name: 'Alibaba',        label: 'Alibaba API Key',       placeholder: 'Enter Alibaba DashScope API Key...',      desc: 'Flagship Qwen reasoning & chat models' },
  openai:     { name: 'OpenAI',         label: 'OpenAI API Key',        placeholder: 'Enter OpenAI API Key (sk-...)...',        desc: 'Flagship GPT-4, GPT-5 & o1 reasoning models' },
  google:     { name: 'Google Gemini',  label: 'Google Gemini API Key', placeholder: 'Enter Google Gemini API Key (AIza...)...', desc: 'Google Gemini multimodal reasoning models' },
  anthropic:  { name: 'Anthropic',      label: 'Anthropic API Key',     placeholder: 'Enter Anthropic API Key (sk-ant-...)...',  desc: 'Claude reasoning & text analysis models' },
  deepseek:   { name: 'DeepSeek',       label: 'DeepSeek API Key',      placeholder: 'Enter DeepSeek API Key (sk-...)...',       desc: 'Highly optimized deep reasoning chat models' },
  glm:        { name: 'GLM',            label: 'GLM API Key',           placeholder: 'Enter GLM API Key (e.g. identifier.secret)...', desc: 'Zhipu AI flagship multilingual chat models' },
  groq:       { name: 'Groq',           label: 'Groq API Key',          placeholder: 'Enter Groq API Key (gsk-...)...',          desc: 'Ultra-fast Llama-3 & Mixtral models' },
  openrouter: { name: 'OpenRouter',     label: 'OpenRouter API Key',    placeholder: 'Enter OpenRouter API Key (sk-or-...)...',  desc: 'Access hundreds of models under a unified API key' },
};

const SEARCH_PROVIDER_IDS = ['tavily', 'serpapi', 'exa'];

const SEARCH_PROVIDER_METADATA: Record<string, { name: string; label: string; placeholder: string; desc: string; docsUrl: string }> = {
  tavily:  { name: 'Tavily',  label: 'Tavily API Key',  placeholder: 'tvly-...',             desc: 'AI-curated web search. Best quality results.',      docsUrl: 'https://app.tavily.com/home' },
  serpapi: { name: 'SerpAPI', label: 'SerpAPI Key',     placeholder: 'Enter SerpAPI key...', desc: 'Real Google Search results via JSON API.',          docsUrl: 'https://serpapi.com/manage-api-key' },
  exa:     { name: 'Exa AI',  label: 'Exa AI API Key',  placeholder: 'Enter Exa API key...', desc: 'Neural semantic search — best for deep research.',  docsUrl: 'https://dashboard.exa.ai/api-keys' },
};

interface DocumentFile {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: 'processing' | 'ready' | 'failed';
  error_message?: string;
  uploaded_at: string;
}

interface SemanticMemory {
  id: string;
  category: 'fact' | 'preference' | 'goal' | 'topic';
  content: string;
  importance_score: number;
  created_at: string;
}

interface RemoteMcpServerItem {
  id: string;
  name: string;
  url: string;
  transport_type: string;
  auth_header?: string | null;
  is_enabled: boolean;
  created_at: string;
  tool_count: number;
  discovered_tools?: { name: string; description: string; schema: any }[];
}


type IngestionStep = {
  id: string;
  icon: React.ElementType;
  label: string;
  detail: string;
};

const INGESTION_STEPS: IngestionStep[] = [
  { id: 'uploading', icon: UploadCloud, label: 'Uploading document',   detail: 'Transmitting file bytes to the server' },
  { id: 'parsing',   icon: FileText,    label: 'Parsing document',     detail: 'Extracting raw text from PDF/DOCX/XLSX' },
  { id: 'chunking',  icon: Scissors,    label: 'Chunking text',        detail: 'Splitting content into semantic segments' },
  { id: 'splitting', icon: Layers,      label: 'Text splitting',       detail: 'Applying recursive character splitter' },
  { id: 'embedding', icon: Cpu,         label: 'Creating embeddings',  detail: 'Encoding chunks into dense vector space' },
  { id: 'storing',   icon: HardDrive,   label: 'Storing in vector DB', detail: 'Writing vectors into Chroma/FAISS index' },
  { id: 'indexing',  icon: Database,    label: 'Indexing complete',    detail: 'Document is ready for semantic retrieval' },
];

const ALL_MODELS = [
  { id: 'gemini-2.5-pro',   label: 'Gemini 2.5 Pro',   provider: 'Google Gemini', apiProvider: 'google' },
  { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', provider: 'Google Gemini', apiProvider: 'google' },
  { id: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash', provider: 'Google Gemini', apiProvider: 'google' },
  { id: 'gemini-1.5-pro',   label: 'Gemini 1.5 Pro',   provider: 'Google Gemini', apiProvider: 'google' },
  { id: 'gpt-4o',           label: 'GPT-4o',           provider: 'OpenAI',        apiProvider: 'openai' },
  { id: 'gpt-4o-mini',      label: 'GPT-4o Mini',      provider: 'OpenAI',        apiProvider: 'openai' },
  { id: 'o1-preview',       label: 'o1 Preview',        provider: 'OpenAI',        apiProvider: 'openai' },
  { id: 'o1-mini',          label: 'o1 Mini',           provider: 'OpenAI',        apiProvider: 'openai' },
  { id: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet', provider: 'Anthropic', apiProvider: 'anthropic' },
  { id: 'claude-3-5-haiku-20241022',  label: 'Claude 3.5 Haiku',  provider: 'Anthropic', apiProvider: 'anthropic' },
  { id: 'claude-3-opus-20240229',     label: 'Claude 3 Opus',      provider: 'Anthropic', apiProvider: 'anthropic' },
  { id: 'deepseek-chat',     label: 'DeepSeek Chat',     provider: 'DeepSeek',  apiProvider: 'deepseek' },
  { id: 'deepseek-reasoner', label: 'DeepSeek Reasoner', provider: 'DeepSeek',  apiProvider: 'deepseek' },
  { id: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B',  provider: 'Groq', apiProvider: 'groq' },
  { id: 'llama-3.1-8b-instant',    label: 'Llama 3.1 8B',   provider: 'Groq', apiProvider: 'groq' },
  { id: 'mixtral-8x7b-32768',      label: 'Mixtral 8x7B',   provider: 'Groq', apiProvider: 'groq' },
  { id: 'openrouter/google/gemini-2.0-flash-exp:free', label: 'Gemini 2.0 Flash (OR)', provider: 'OpenRouter', apiProvider: 'openrouter' },
  { id: 'openrouter/meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B (OR)',  provider: 'OpenRouter', apiProvider: 'openrouter' },
  { id: 'glm-4-plus', label: 'GLM-4 Plus', provider: 'GLM',     apiProvider: 'glm' },
  { id: 'glm-4-air',  label: 'GLM-4 Air',  provider: 'GLM',     apiProvider: 'glm' },
  { id: 'qwen-max',   label: 'Qwen Max',   provider: 'Alibaba', apiProvider: 'alibaba' },
  { id: 'qwen-plus',  label: 'Qwen Plus',  provider: 'Alibaba', apiProvider: 'alibaba' },
  { id: 'qwen-turbo', label: 'Qwen Turbo', provider: 'Alibaba', apiProvider: 'alibaba' },
];

async function detectUserLocation(): Promise<string> {
  if ('geolocation' in navigator) {
    try {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 6000, enableHighAccuracy: true });
      });
      const { latitude, longitude } = pos.coords;
      const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json`);
      if (res.ok) {
        const data = await res.json();
        const address = data.address || {};
        const parts = [
          address.suburb || address.neighbourhood || address.residential || address.village,
          address.city || address.town || address.county,
          address.state,
          address.country
        ].filter(Boolean);
        if (parts.length > 0) return parts.join(', ');
      }
    } catch (e) {
      console.warn('Geolocation API unavailable or permission denied, trying IP fallback:', e);
    }
  }

  try {
    const ipRes = await fetch('https://ipapi.co/json/').catch(() => null);
    if (ipRes && ipRes.ok) {
      const ipData = await ipRes.json();
      const parts = [ipData.city, ipData.region, ipData.country_name].filter(Boolean);
      if (parts.length > 0) return parts.join(', ');
    }
  } catch { /* fallback */ }

  return 'Mithapur, Bihar, India';
}

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€ Premium Toggle Switch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const Toggle = memo(function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onChange(!checked);
    }
  }, [checked, onChange]);

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
      onKeyDown={handleKeyDown}
      className={`relative inline-flex w-11 h-6 rounded-full flex-shrink-0 cursor-pointer p-0.5
        transition-colors duration-200 ease-in-out outline-none
        focus-visible:ring-2 focus-visible:ring-blue-500/40 active:scale-[0.96]
        ${checked
          ? 'bg-blue-600 shadow-[0_0_12px_rgba(37,99,235,0.35)]'
          : 'bg-[#222225] border border-[#333338] hover:bg-[#2a2a2e]'
        }`}
    >
      <span
        className={`pointer-events-none inline-block w-5 h-5 rounded-full bg-white shadow-md transform
          transition-transform duration-200 ease-in-out
          ${checked ? 'translate-x-5' : 'translate-x-0 bg-[#8e8e93]'}`}
      />
    </button>
  );
});

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€ Setting Row â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const SettingRow = memo(function SettingRow({
  label, desc, children, danger,
}: { label: string; desc?: string; children: React.ReactNode; danger?: boolean }) {
  return (
    <div className={`settings-row flex items-center justify-between py-4 border-b border-border last:border-0 gap-4
      ${danger ? 'text-rose-400' : 'text-foreground'}`}
    >
      <div className="min-w-0">
        <p className="text-sm font-semibold text-foreground">{label}</p>
        {desc && <p className="text-[11px] text-foreground-2 mt-1 leading-relaxed">{desc}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
});

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€ Section Card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const SectionCard = memo(function SectionCard({
  title, children,
}: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-surface overflow-hidden shadow-sm transition-colors duration-200">
      <div className="settings-card-header px-4 py-3 bg-surface-2/60 border-b border-border">
        <h3 className="text-[10px] font-bold uppercase tracking-wider text-foreground-3">{title}</h3>
      </div>
      <div className="settings-card-body px-4 divide-y divide-border/80">{children}</div>
    </div>
  );
});

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€ Ingestion Progress â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const IngestionProgress = memo(function IngestionProgress({
  filename, currentStep, done, error,
}: {
  filename: string; currentStep: number; done: boolean; error: string | null;
}) {
  return (
    <div className="mt-4 p-4 rounded-xl border border-border bg-surface-2/50 space-y-3">
      <div className="flex items-center gap-2">
        {done ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
        ) : error ? (
          <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
        ) : (
          <Loader2 className="w-4 h-4 text-blue-500 animate-spin flex-shrink-0" />
        )}
        <p className="text-xs font-semibold text-foreground truncate">
          {done ? 'Ingestion complete!' : error ? 'Ingestion failed' : `Processing: ${filename}`}
        </p>
      </div>

      {error && (
        <p className="text-[10px] text-rose-400 bg-rose-950/20 border border-rose-900/30 rounded-lg px-3 py-2 leading-relaxed">
          {error}
        </p>
      )}

      {!error && (
        <div className="space-y-1.5">
          {INGESTION_STEPS.map((step, idx) => {
            const StepIcon = step.icon;
            const isActive = idx === currentStep && !done;
            const isDone   = done ? true : idx < currentStep;
            return (
              <div key={step.id} className="flex items-center gap-2.5">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300
                  ${isDone   ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-400'
                  : isActive  ? 'bg-blue-500/15 border border-blue-500/30 text-blue-400'
                             : 'bg-surface-3 border border-border text-foreground-3 opacity-50'}`}>
                  {isDone
                    ? <Check className="w-2.5 h-2.5" />
                    : <StepIcon className="w-2.5 h-2.5" />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-[10px] font-semibold leading-none ${isDone ? 'text-emerald-400' : isActive ? 'text-blue-400' : 'text-foreground-3'}`}>
                    {step.label}
                  </p>
                  {isActive && (
                    <p className="text-[9px] text-foreground-3 mt-0.5 leading-normal">{step.detail}</p>
                  )}
                </div>
                {isActive && (
                  <div className="w-12 h-1 rounded-full bg-surface-3 overflow-hidden flex-shrink-0">
                    <div
                      className="h-full rounded-full animate-shimmer"
                      style={{
                        background: 'linear-gradient(90deg, rgba(59,130,246,0.3) 0%, rgba(59,130,246,1) 50%, rgba(59,130,246,0.3) 100%)',
                        backgroundSize: '200% 100%',
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
});

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€ Pipeline Explainer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const PipelineExplainer = memo(function PipelineExplainer() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border bg-surface-2/30 overflow-hidden transition-colors duration-200">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2.5 px-4 py-3 text-left hover:bg-surface-2/80 transition-colors duration-150"
      >
        <Info className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
        <span className="text-xs font-semibold text-foreground flex-1">How document ingestion works</span>
        <ChevronRight className={`w-3.5 h-3.5 text-foreground-3 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3 animate-slide-up">
          <div className="h-px bg-border" />
          <p className="text-[11px] text-foreground-2 leading-relaxed">
            When you upload a document, openChat runs a multi-stage ingestion pipeline to make it searchable by the AI:
          </p>
          <div className="grid gap-2">
            {[
              { icon: FileText, title: '1. Parse', body: 'The raw file (PDF, DOCX, XLSX) is read and its text content is extracted by a specialised parser.' },
              { icon: Scissors, title: '2. Chunk', body: 'The extracted text is split into smaller, overlapping segments (chunks) using a recursive character splitter to preserve sentence context.' },
              { icon: Cpu,      title: '3. Embed', body: 'Each chunk is passed through an embedding model which converts it into a high-dimensional vector capturing semantic meaning.' },
              { icon: Database, title: '4. Index', body: 'The vectors are stored in a local vector database. At query time, the AI retrieves similar chunks and injects them as context.' },
            ].map(({ icon: Icon, title, body }) => (
              <div key={title} className="flex gap-2.5 p-2.5 rounded-lg bg-surface border border-border">
                <div className="w-6 h-6 rounded-md bg-blue-500/10 border border-blue-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Icon className="w-3 h-3 text-blue-400" />
                </div>
                <div>
                  <p className="text-[10px] font-bold text-foreground">{title}</p>
                  <p className="text-[10px] text-foreground-3 leading-relaxed mt-0.5">{body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€ API Key Field â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const ApiKeyField = memo(function ApiKeyField({
  provider, initialMaskedKey, status, lastError, onSaveSuccess, onDeleteSuccess,
}: {
  provider: string;
  initialMaskedKey: string;
  status: string;
  lastError: string | null;
  onSaveSuccess: (updatedProvider: Provider) => void;
  onDeleteSuccess: () => void;
}) {
  const [val, setVal]           = useState(initialMaskedKey);
  const [show, setShow]         = useState(false);
  const [saveStep, setSaveStep] = useState<string>('');
  const [loading, setLoading]   = useState(false);
  const [errorMsg, setErrorMsg] = useState(lastError || '');

  useEffect(() => {
    const localHasKey = ProviderKeyManager.hasKey(provider);
    setVal(initialMaskedKey || (localHasKey ? 'â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢' : ''));
    setErrorMsg(lastError || '');
    setSaveStep('');
    setLoading(false);
  }, [initialMaskedKey, lastError, provider]);

  const handleInputChange = useCallback((newVal: string) => {
    setVal(newVal);
    setErrorMsg('');
  }, []);

  const handleSave = useCallback(async () => {
    if (!val.trim() || loading) return;
    setLoading(true);
    setErrorMsg('');
    try {
      setSaveStep('Encrypting & Verifying Key...');
      await ProviderKeyManager.verifyKey(provider, val);
      setSaveStep('Fetching Providers...');
      const data = await apiRequest('/providers');
      useChatStore.getState().setProviders(data);
      const updated = data.find((p: Provider) => p.id === provider);
      if (updated) {
        onSaveSuccess(updated);
        setVal(updated.saved ? 'â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢' : '');
      }
    } catch (err: unknown) {
      setSaveStep('');
      setErrorMsg((err as Error).message || 'Verification failed. Check that your key is valid.');
    } finally {
      setLoading(false);
      setSaveStep('');
    }
  }, [val, loading, provider, onSaveSuccess]);

  const handleDelete = useCallback(async () => {
    try {
      setLoading(true);
      await apiRequest(`/api-keys/${provider}`, { method: 'DELETE' });
      ProviderKeyManager.removeKey(provider);
      const data = await apiRequest('/providers');
      useChatStore.getState().setProviders(data);
      setVal('');
      setErrorMsg('');
      setSaveStep('');
      onDeleteSuccess();
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setLoading(false);
    }
  }, [provider, onDeleteSuccess]);

  const isVerified = status === 'VERIFIED';
  const meta = PROVIDER_METADATA[provider] || { label: provider, placeholder: 'Enter key...' };

  return (
    <div className="space-y-2 mt-3 bg-surface-2 p-3.5 rounded-xl border border-border animate-fade-in">
      <div className="flex items-center justify-between">
        <label className="text-[11px] font-semibold text-foreground-2 flex items-center gap-1.5">
          <Key className="w-3.5 h-3.5 text-foreground-3" />
          {meta.label}
        </label>
        <div className="flex items-center gap-1.5">
          {loading && saveStep && (
            <span className="text-[10px] text-blue-400 font-medium flex items-center gap-1">
              <Loader2 className="w-2.5 h-2.5 animate-spin" /> {saveStep}
            </span>
          )}
          {!loading && isVerified && (
            <span className="text-[10px] text-emerald-400 font-semibold flex items-center gap-1">
              <Check className="w-2.5 h-2.5" /> Verified
            </span>
          )}
          {!loading && status === 'INVALID' && (
            <span className="text-[10px] text-rose-400 font-medium flex items-center gap-1">
              <AlertCircle className="w-2.5 h-2.5" /> Invalid Key
            </span>
          )}
          {!loading && status === 'ERROR' && (
            <span className="text-[10px] text-rose-400 font-medium flex items-center gap-1">
              <AlertCircle className="w-2.5 h-2.5" /> Provider Error
            </span>
          )}
        </div>
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            id={`key-input-${provider}`}
            type={show ? 'text' : 'password'}
            value={val}
            readOnly={isVerified || loading}
            onChange={(e) => handleInputChange(e.target.value)}
            placeholder={initialMaskedKey ? 'â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢' : `Enter ${meta.label}...`}
            className={`w-full bg-background border rounded-lg px-3 py-2 pr-9 text-xs font-mono text-foreground
              placeholder:text-foreground-3 focus:outline-none transition-all duration-150 shadow-inner
              ${isVerified
                ? 'border-emerald-900/40 text-foreground-3 cursor-default select-none'
                : 'border-border focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50'}`}
          />
          {!isVerified && !loading && (
            <button
              type="button"
              onClick={() => setShow((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-foreground-3 hover:text-foreground-2 transition-colors duration-150"
            >
              {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>

        {isVerified ? (
          <button
            onClick={handleDelete}
            className="px-3.5 py-2 rounded-lg text-xs font-semibold border shadow-sm bg-surface-3 border-border text-foreground hover:bg-surface hover:text-foreground active:scale-[0.98] flex items-center gap-1.5 flex-shrink-0 transition-all duration-150"
          >
            Change
          </button>
        ) : (
          <button
            onClick={handleSave}
            disabled={loading || !val.trim()}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold transition-all duration-150 flex items-center gap-1.5 flex-shrink-0 border shadow-sm
              ${loading
                ? 'bg-surface-3 border-border text-foreground-3 cursor-not-allowed'
                : !val.trim()
                ? 'bg-surface-3 border-border text-foreground-3 cursor-not-allowed'
                : 'bg-blue-600 border-blue-700 text-white hover:bg-blue-500 active:scale-[0.98]'}`}
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {loading ? 'Processing' : 'Verify & Save'}
          </button>
        )}

        {initialMaskedKey && (
          <button
            onClick={handleDelete}
            className="px-2.5 rounded-lg border border-border bg-background hover:bg-surface text-foreground-3 hover:text-rose-400 flex items-center justify-center flex-shrink-0 transition-all duration-150 shadow-sm"
            aria-label="Remove key"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {errorMsg && (
        <p className="text-[10px] text-rose-400 leading-normal mt-1.5 bg-rose-950/20 border border-rose-900/30 p-2.5 rounded-lg">
          {errorMsg}
        </p>
      )}
    </div>
  );
});

// â”€â”€ Custom Select Options â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const THEME_OPTIONS: SelectOption[] = [
  { value: 'system', label: 'System', icon: Monitor, description: 'Sync with OS settings' },
  { value: 'dark', label: 'Dark', icon: Moon, description: 'Sleek pitch dark theme' },
  { value: 'light', label: 'Light', icon: Sun, description: 'Clean light mode' },
];

const CONTRAST_OPTIONS: SelectOption[] = [
  { value: 'system', label: 'System', icon: Monitor, description: 'Match system contrast' },
  { value: 'default', label: 'Default', icon: Eye, description: 'Standard UI contrast' },
  { value: 'high', label: 'High contrast', icon: Zap, description: 'Max contrast & borders' },
];

const ACCENT_OPTIONS: SelectOption[] = [
  { value: 'default', label: 'Default (Blue)', color: '#3b82f6', description: 'Electric Blue' },
  { value: 'emerald', label: 'Emerald', color: '#10b981', description: 'Vibrant Green' },
  { value: 'indigo', label: 'Indigo', color: '#6366f1', description: 'Deep Indigo' },
  { value: 'amber', label: 'Amber', color: '#f59e0b', description: 'Warm Amber' },
  { value: 'rose', label: 'Rose', color: '#f43f5e', description: 'Vivid Rose' },
  { value: 'violet', label: 'Violet', color: '#8b5cf6', description: 'Royal Violet' },
];

const LANGUAGE_OPTIONS: SelectOption[] = [
  { value: 'Auto-detect', label: 'Auto-detect', icon: Globe, description: 'Automatic detection' },
  { value: 'English', label: 'English', description: 'English (US)' },
  { value: 'Hindi', label: 'Hindi', description: 'à¤¹à¤¿à¤¨à¥à¤¦à¥€' },
  { value: 'Spanish', label: 'Spanish', description: 'EspaÃ±ol' },
  { value: 'French', label: 'French', description: 'FranÃ§ais' },
  { value: 'German', label: 'German', description: 'Deutsch' },
  { value: 'Japanese', label: 'Japanese', description: 'æ—¥æœ¬èªž' },
  { value: 'Chinese', label: 'Chinese', description: 'ä¸­æ–‡' },
];

const FONT_SIZE_OPTIONS: SelectOption[] = [
  { value: 'sm', label: 'Small', icon: Type, description: '13px compact scaling' },
  { value: 'base', label: 'Default', icon: Type, description: '15px standard size' },
  { value: 'lg', label: 'Large', icon: Type, description: '17px enhanced scale' },
];

const MEMORY_CATEGORY_OPTIONS: SelectOption[] = [
  { value: 'fact', label: 'Fact', description: 'Core user fact' },
  { value: 'preference', label: 'Preference', description: 'User preference' },
  { value: 'goal', label: 'Goal', description: 'User objective' },
  { value: 'topic', label: 'Topic', description: 'Subject area' },
];

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€ Main Settings Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function SettingsPage() {
  // â”€â”€ Routing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = (searchParams.get('tab') as SettingsTab) || 'general';

  const contentRef = useRef<HTMLDivElement>(null);

  const setTab = useCallback((newTab: SettingsTab) => {
    setSearchParams({ tab: newTab }, { replace: true });
  }, [setSearchParams]);

  // Scroll to top of content panel whenever tab changes
  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: 'instant' });
  }, [tab]);

  // ——— Global Stores ——————————————————————————————————————————————
  const {
    theme, setTheme,
    contrastMode, setContrastMode,
    accentColor, setAccentColor,
    fontSize, setFontSize,
    language, setLanguage,
    higherIntelligence, setHigherIntelligence,
    enableDictation, setEnableDictation,
    developerMode, toggleDeveloperMode,
    compactMode, setCompactMode,
  } = useUIStore();
  const { user, logout } = useAuthStore();
  const {
    activeModel, setActiveModel,
    setChats, setActiveChatId, setMessages, chats,
    providers, setProviders,
    keysLoading, setKeysLoading,
  } = useChatStore();
  const token = useAuthStore((state) => state.token);

  // ——— Generation settings (persist in localStorage) ———————————————
  const [temperature, setTemperatureState] = useState<number>(
    () => parseFloat(localStorage.getItem('llm_temperature') || '0.7'),
  );
  const [maxTokens, setMaxTokensState]     = useState<number>(
    () => parseInt(localStorage.getItem('llm_max_tokens') || '2048', 10),
  );
  const [streaming, setStreamingState]     = useState<boolean>(
    () => localStorage.getItem('llm_streaming') !== 'false',
  );

  // ——— Feature flags (persist immediately on change) ———————————————
  const [memoryEnabled, setMemoryState] = useState<boolean>(
    () => localStorage.getItem('feature_memory') !== 'false',
  );
  const [ragEnabled, setRagState]       = useState<boolean>(
    () => localStorage.getItem('feature_rag') !== 'false',
  );
  const [toolsEnabled, setToolsState]   = useState<boolean>(
    () => localStorage.getItem('feature_tools') !== 'false',
  );
  const [webEnabled, setWebState]       = useState<boolean>(
    () => localStorage.getItem('feature_web') !== 'false',
  );

  // Persist feature flags immediately
  const setMemoryEnabled = useCallback((v: boolean) => {
    localStorage.setItem('feature_memory', String(v));
    setMemoryState(v);
  }, []);
  const setRagEnabled = useCallback((v: boolean) => {
    localStorage.setItem('feature_rag', String(v));
    setRagState(v);
  }, []);
  const setToolsEnabled = useCallback((v: boolean) => {
    localStorage.setItem('feature_tools', String(v));
    setToolsState(v);
  }, []);
  const setWebEnabled = useCallback((v: boolean) => {
    localStorage.setItem('feature_web', String(v));
    setWebState(v);
  }, []);



  // ── UI state ──────────────────────────────────────────────
  const [saved, setSaved]               = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const { toasts, removeToast, addToast } = useToast();
  const [editModes, setEditModes]       = useState<Record<string, boolean>>({});
  const [refreshing, setRefreshing]     = useState(false);
  const providerCardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // ── Data Controls state ───────────────────────────────────────
  const [improveModel, setImproveModel] = useState<boolean>(
    () => localStorage.getItem('omni_improve_model') !== 'false',
  );
  const [locationEnabled, setLocationEnabled] = useState<boolean>(
    () => localStorage.getItem('omni_location_enabled') !== 'false',
  );
  const [userLocation, setUserLocation] = useState<string | null>(
    () => localStorage.getItem('omni_user_location')
  );
  const [locationLoading, setLocationLoading] = useState<boolean>(false);
  const [showSharedLinksModal, setShowSharedLinksModal] = useState(false);
  const [showArchivedChatsModal, setShowArchivedChatsModal] = useState(false);
  const [archiveRefresh, setArchiveRefresh] = useState(0); // forces re-read of localStorage

  const toggleImproveModel = useCallback((v: boolean) => {
    localStorage.setItem('omni_improve_model', String(v));
    setImproveModel(v);
    addToast(
      v
        ? 'Model telemetry enabled. Anonymous logs optimize response quality.'
        : 'Model telemetry disabled.',
      'info'
    );
  }, [addToast]);

  const toggleLocationEnabled = useCallback(async (active: boolean) => {
    localStorage.setItem('omni_location_enabled', String(active));
    setLocationEnabled(active);

    if (active) {
      setLocationLoading(true);
      try {
        const loc = await detectUserLocation();
        localStorage.setItem('omni_user_location', loc);
        setUserLocation(loc);
        addToast(`Location context active: ${loc}`, 'success');
      } catch {
        const fallback = 'Mithapur, Bihar, India';
        localStorage.setItem('omni_user_location', fallback);
        setUserLocation(fallback);
        addToast(`Location set to: ${fallback}`, 'info');
      } finally {
        setLocationLoading(false);
      }
    } else {
      localStorage.removeItem('omni_user_location');
      setUserLocation(null);
      addToast('Location context disabled.', 'info');
    }
  }, [addToast]);

  useEffect(() => {
    if (locationEnabled && !userLocation && !locationLoading) {
      setLocationLoading(true);
      detectUserLocation().then((loc) => {
        localStorage.setItem('omni_user_location', loc);
        setUserLocation(loc);
        setLocationLoading(false);
      });
    }
  }, [locationEnabled, userLocation, locationLoading]);

  const archivedChatIds: string[] = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem('omni_archived_chats') || '[]');
    } catch {
      return [];
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chats, archiveRefresh]);

  const archivedChatsList = useMemo(() => {
    return chats.filter((c) => archivedChatIds.includes(c.id));
  }, [chats, archivedChatIds]);

  const handleUnarchiveChat = useCallback((chatId: string) => {
    const updated = archivedChatIds.filter((id) => id !== chatId);
    localStorage.setItem('omni_archived_chats', JSON.stringify(updated));
    setArchiveRefresh((n) => n + 1);
    addToast('Chat unarchived.', 'success');
  }, [archivedChatIds, addToast]);

  const handleDeleteArchivedChat = useCallback((chatId: string) => {
    useChatStore.getState().removeChat(chatId);
    const updated = archivedChatIds.filter((id) => id !== chatId);
    localStorage.setItem('omni_archived_chats', JSON.stringify(updated));
    setArchiveRefresh((n) => n + 1);
    addToast('Chat deleted.', 'success');
  }, [archivedChatIds, addToast]);

  const handleArchiveAllChats = useCallback(() => {
    const allIds = chats.map((c) => c.id);
    localStorage.setItem('omni_archived_chats', JSON.stringify(allIds));
    setArchiveRefresh((n) => n + 1);
    addToast('All active chats have been archived.', 'success');
  }, [chats, addToast]);


  // â”€â”€ Documents state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const [documents, setDocuments]         = useState<DocumentFile[]>([]);
  const [uploading, setUploading]         = useState(false);
  const [uploadError, setUploadError]     = useState<string | null>(null);
  const [ingestFilename, setIngestFilename] = useState<string>('');
  const [ingestStep, setIngestStep]       = useState<number>(-1);
  const [ingestDone, setIngestDone]       = useState(false);
  const ingestTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // â”€â”€ Memories state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const [memories, setMemories]           = useState<SemanticMemory[]>([]);
  const [memContent, setMemContent]       = useState('');
  const [memCategory, setMemCategory]     = useState<'fact' | 'preference' | 'goal' | 'topic'>('fact');
  const [memImportance, setMemImportance] = useState(5);
  const [memError, setMemError]           = useState<string | null>(null);

  // Remote MCP Servers state
  const [mcpServers, setMcpServers]               = useState<RemoteMcpServerItem[]>([]);
  const [isLoadingMcp, setIsLoadingMcp]           = useState(false);
  const [mcpName, setMcpName]                     = useState('');
  const [mcpUrl, setMcpUrl]                       = useState('');
  const [mcpAuth, setMcpAuth]                     = useState('');
  const [mcpTransport, setMcpTransport]           = useState('http_jsonrpc');
  const [mcpTestResult, setMcpTestResult]         = useState<any | null>(null);
  const [isTestingMcp, setIsTestingMcp]           = useState(false);
  const [isSavingMcp, setIsSavingMcp]             = useState(false);

  // Data fetching
  const fetchDocuments = useCallback(async () => {
    try {
      const data = await apiRequest('/documents');
      setDocuments(data);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  }, []);

  const fetchMemories = useCallback(async () => {
    try {
      const data = await apiRequest('/memories');
      setMemories(data);
    } catch (err) {
      console.error('Failed to load memories:', err);
    }
  }, []);

  const fetchMcpServers = useCallback(async () => {
    setIsLoadingMcp(true);
    try {
      const data = await apiRequest('/mcp/servers');
      setMcpServers(data);
    } catch (err) {
      console.error('Failed to load MCP servers:', err);
    } finally {
      setIsLoadingMcp(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'documents') fetchDocuments();
    else if (tab === 'memories') fetchMemories();
    else if (tab === 'mcpservers') fetchMcpServers();
  }, [tab, fetchDocuments, fetchMemories, fetchMcpServers]);

  const handleTestMcpConnection = async () => {
    if (!mcpUrl.trim()) {
      addToast('Please enter a remote MCP server URL to test.', 'error');
      return;
    }
    setIsTestingMcp(true);
    setMcpTestResult(null);
    try {
      const result = await apiRequest('/mcp/servers/test', {
        method: 'POST',
        json: {
          url: mcpUrl.trim(),
          auth_header: mcpAuth.trim() || undefined,
          transport_type: mcpTransport,
        }
      });
      setMcpTestResult(result);
      if (result.status === 'success') {
        addToast(`Connected successfully! Discovered ${result.tool_count} tools (${result.latency_ms}ms)`, 'success');
      } else {
        addToast(`Connection test failed: ${result.message}`, 'error');
      }
    } catch (err: any) {
      addToast(err.message || 'Failed to test remote MCP server.', 'error');
    } finally {
      setIsTestingMcp(false);
    }
  };

  const handleAddMcpServer = async () => {
    if (!mcpName.trim() || !mcpUrl.trim()) {
      addToast('Server Name and Server URL are required.', 'error');
      return;
    }
    setIsSavingMcp(true);
    try {
      await apiRequest('/mcp/servers', {
        method: 'POST',
        json: {
          name: mcpName.trim(),
          url: mcpUrl.trim(),
          auth_header: mcpAuth.trim() || undefined,
          transport_type: mcpTransport,
        }
      });
      addToast('Remote MCP Server added and tools registered successfully!', 'success');
      setMcpName('');
      setMcpUrl('');
      setMcpAuth('');
      setMcpTestResult(null);
      fetchMcpServers();
    } catch (err: any) {
      addToast(err.message || 'Failed to register remote MCP server.', 'error');
    } finally {
      setIsSavingMcp(false);
    }
  };

  const handleToggleMcpServer = async (id: string, currentEnabled: boolean) => {
    try {
      await apiRequest(`/mcp/servers/${id}`, {
        method: 'PATCH',
        json: { is_enabled: !currentEnabled }
      });
      addToast(`Server ${!currentEnabled ? 'enabled' : 'disabled'} successfully.`, 'success');
      fetchMcpServers();
    } catch (err: any) {
      addToast(err.message || 'Failed to update MCP server status.', 'error');
    }
  };

  const handleDeleteMcpServer = async (id: string) => {
    try {
      await apiRequest(`/mcp/servers/${id}`, { method: 'DELETE' });
      addToast('Remote MCP Server deleted.', 'success');
      fetchMcpServers();
    } catch (err: any) {
      addToast(err.message || 'Failed to delete MCP server.', 'error');
    }
  };



  // Clean up ingestion timer
  useEffect(() => {
    return () => {
      if (ingestTimerRef.current) clearTimeout(ingestTimerRef.current as unknown as number);
    };
  }, []);

  // Apply font size on mount
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('font-sm', 'font-lg');
    if (fontSize === 'sm') root.classList.add('font-sm');
    if (fontSize === 'lg') root.classList.add('font-lg');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // â”€â”€ Providers / Models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const fetchProviders = useCallback(async () => {
    setKeysLoading(true);
    try {
      const data = await ProviderKeyManager.sync();
      setProviders(data);
      const initialEditModes: Record<string, boolean> = {};
      data.forEach((p: Provider) => {
        if (p.saved) initialEditModes[p.id] = true;
      });
      setEditModes((prev) => ({ ...prev, ...initialEditModes }));
    } catch (err) {
      console.error('Failed to fetch providers:', err);
    } finally {
      setKeysLoading(false);
    }
  }, [setKeysLoading, setProviders]);

  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  const verifiedProviderIds = new Set(
    providers.filter((p) => p.status === 'VERIFIED').map((p) => p.id),
  );

  const apiModels = providers
    .filter((p) => p.status === 'VERIFIED')
    .flatMap((p) =>
      p.availableModels.map((m) => ({
        id: m, label: m,
        provider: PROVIDER_METADATA[p.id]?.name || p.id,
        apiProvider: p.id,
      })),
    );

  const staticIds = new Set(ALL_MODELS.map((m) => m.id));
  const extraApiModels = apiModels.filter((m) => !staticIds.has(m.id));
  const combinedModels = [...ALL_MODELS, ...extraApiModels];
  const uniqueModelsMap = new Map();
  combinedModels.forEach((m) => {
    if (!uniqueModelsMap.has(m.id)) {
      uniqueModelsMap.set(m.id, m);
    }
  });
  const availableModelsList = Array.from(uniqueModelsMap.values());
  const readyModels = availableModelsList.filter((m) => verifiedProviderIds.has(m.apiProvider));

  useEffect(() => {
    if (!keysLoading && readyModels.length > 0) {
      if (!readyModels.some((m) => m.id === activeModel)) {
        setActiveModel(readyModels[0].id);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keysLoading, readyModels.length]);

  // â”€â”€ Handlers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const handleSaveGeneration = useCallback(() => {
    localStorage.setItem('llm_temperature', String(temperature));
    localStorage.setItem('llm_max_tokens', String(maxTokens));
    localStorage.setItem('llm_streaming', String(streaming));
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  }, [temperature, maxTokens, streaming]);

  const handleDeleteConversations = useCallback(() => {
    if (!deleteConfirm) { setDeleteConfirm(true); return; }
    // Immediate 0ms optimistic update
    setChats([]);
    setActiveChatId(null);
    setMessages([]);
    setDeleteConfirm(false);
    // Background network request
    apiRequest('/chats/all', { method: 'DELETE' }).catch((err) => {
      console.error('Failed to delete all conversations:', err);
    });
  }, [deleteConfirm, setChats, setActiveChatId, setMessages]);

  const handleExportData = useCallback(() => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(chats, null, 2));
    const a = document.createElement('a');
    a.setAttribute('href', dataStr);
    a.setAttribute('download', `omni-export-${Date.now()}.json`);
    document.body.appendChild(a);
    a.click();
    a.remove();
  }, [chats]);

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login');
  }, [logout, navigate]);

  const handleManualRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const refreshed = await apiRequest('/providers/refresh', { method: 'POST' });
      setProviders(refreshed);
    } catch (err) {
      console.error('Manual refresh failed:', err);
    } finally {
      setRefreshing(false);
    }
  }, [setProviders]);

  const handleToggleProvider = useCallback(async (provId: string, active: boolean) => {
    if (active) {
      setEditModes((prev) => ({ ...prev, [provId]: true }));
      setTimeout(() => {
        document.getElementById(`key-input-${provId}`)?.focus();
      }, 50);
    } else {
      setEditModes((prev) => ({ ...prev, [provId]: false }));
      try {
        await apiRequest(`/api-keys/${provId}`, { method: 'DELETE' });
        ProviderKeyManager.removeKey(provId);
        const data = await apiRequest('/providers');
        setProviders(data);
      } catch (err) {
        console.error('Failed to delete key on toggle off:', err);
      }
    }
  }, [setProviders]);

  const handleFocusProviderKey = useCallback((apiProvider: string) => {
    if (apiProvider === 'none') return;
    setEditModes((prev) => ({ ...prev, [apiProvider]: true }));
    setTimeout(() => {
      providerCardRefs.current[apiProvider]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      document.getElementById(`key-input-${apiProvider}`)?.focus();
    }, 100);
  }, []);

  // â”€â”€ Ingestion progress â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const startIngestionProgress = useCallback((filename: string) => {
    setIngestFilename(filename);
    setIngestStep(0);
    setIngestDone(false);
    setUploadError(null);

    let step = 0;
    const STEP_DURATIONS = [600, 900, 800, 700, 1200, 800];

    const advance = () => {
      step += 1;
      setIngestStep(step);
      if (step < STEP_DURATIONS.length) {
        ingestTimerRef.current = setTimeout(advance, STEP_DURATIONS[step]) as unknown as ReturnType<typeof setInterval>;
      }
    };
    ingestTimerRef.current = setTimeout(advance, STEP_DURATIONS[0]) as unknown as ReturnType<typeof setInterval>;
  }, []);

  const pollUntilReady = useCallback(async (docId: string) => {
    const MAX_POLLS = 30;
    let polls = 0;
    const interval = setInterval(async () => {
      polls++;
      try {
        const docs: DocumentFile[] = await apiRequest('/documents');
        setDocuments(docs);
        const doc = docs.find((d) => d.id === docId);
        if (doc && doc.status === 'ready') {
          clearInterval(interval);
          if (ingestTimerRef.current) clearTimeout(ingestTimerRef.current as unknown as number);
          setIngestStep(6);
          setIngestDone(true);
          setUploading(false);
        } else if (doc && doc.status === 'failed') {
          clearInterval(interval);
          if (ingestTimerRef.current) clearTimeout(ingestTimerRef.current as unknown as number);
          setUploadError('Indexing failed on the server. Please try again.');
          setIngestStep(-1);
          setUploading(false);
        }
      } catch { /* ignore */ }
      if (polls >= MAX_POLLS) {
        clearInterval(interval);
        setIngestDone(true);
        setIngestStep(6);
        setUploading(false);
      }
    }, 2000);
  }, []);

  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const file = files[0];
    e.target.value = '';
    setUploading(true);
    setUploadError(null);
    setIngestDone(false);
    setIngestStep(-1);

    const formData = new FormData();
    formData.append('file', file);
    try {
      startIngestionProgress(file.name);
      const response = await fetch('/api/v1/documents/upload', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'File upload failed');
      }
      const doc: DocumentFile = await response.json();
      setDocuments((prev) => [doc, ...prev.filter((d) => d.id !== doc.id)]);
      pollUntilReady(doc.id);
    } catch (err: unknown) {
      if (ingestTimerRef.current) clearTimeout(ingestTimerRef.current as unknown as number);
      setUploadError((err as Error).message || 'Failed to upload document');
      setIngestStep(-1);
      setUploading(false);
    }
  }, [token, startIngestionProgress, pollUntilReady]);

  const handleDeleteDoc = useCallback(async (id: string) => {
    try {
      await apiRequest(`/documents/${id}`, { method: 'DELETE' });
      setDocuments((prev) => prev.filter((doc) => doc.id !== id));
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  }, []);

  const handleAddMemory = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!memContent.trim()) return;
    setMemError(null);
    try {
      const newMemory = await apiRequest('/memories', {
        method: 'POST',
        json: { category: memCategory, content: memContent.trim(), importance_score: memImportance },
      });
      setMemories((prev) => [newMemory, ...prev]);
      setMemContent('');
      setMemImportance(5);
    } catch (err: unknown) {
      setMemError((err as Error).message || 'Failed to record memory');
    }
  }, [memContent, memCategory, memImportance]);

  const handleDeleteMemory = useCallback(async (id: string) => {
    try {
      await apiRequest(`/memories/${id}`, { method: 'DELETE' });
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch (err) {
      console.error('Failed to delete memory:', err);
    }
  }, []);

  // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  // Render
  // â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-background text-foreground transition-colors duration-250">
      <ToastContainer toasts={toasts} onRemove={removeToast} />
      <div className="w-full max-w-[1400px] mx-auto px-4 md:px-8 py-6 flex-1 flex flex-col min-h-0 space-y-5 animate-fade-in-up">

        {/* Header */}
        <div className="flex justify-between items-center flex-shrink-0">
          <div>
            <h1 className="text-xl font-semibold text-foreground tracking-tight">Settings</h1>
            <p className="text-foreground-2 text-xs mt-1">Configure your workspace and AI preferences</p>
          </div>
          {tab === 'models' && (
            <button
              onClick={handleManualRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-border bg-surface hover:bg-surface-2 text-foreground-2 text-xs font-bold transition-all duration-150 shadow-sm active:scale-[0.98] disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-blue-500' : ''}`} />
              <span>{refreshing ? 'Refreshing...' : 'Refresh Status'}</span>
            </button>
          )}
        </div>

        <div className="flex-1 min-h-0 flex flex-col lg:flex-row gap-0 rounded-2xl border border-border overflow-hidden shadow-2xl bg-surface transition-colors duration-250">

          {/* Sidebar */}
          <aside className="settings-sidebar w-full lg:w-60 flex-shrink-0 flex lg:flex-col gap-1 bg-background p-4 border-b lg:border-b-0 lg:border-r border-border overflow-y-auto custom-scrollbar transition-colors duration-250">
            {TABS.map(({ id, label, icon: Icon }) => {
              const isChat   = id === 'chat';
              const isActive = !isChat && tab === id;
              return (
                <div key={id} className="w-full">
                  <button
                    onClick={() => isChat ? navigate('/') : setTab(id as SettingsTab)}
                    className={`group w-full flex items-center justify-center lg:justify-start gap-3 px-3.5 py-3 rounded-xl
                      text-xs font-semibold whitespace-nowrap relative overflow-hidden transition-all duration-[180ms]
                      ${isActive
                        ? 'bg-surface-2 text-foreground shadow-sm'
                        : 'text-foreground-2 hover:text-foreground hover:bg-surface-3/50'
                      }`}
                  >
                    {/* Blue left indicator for active tab */}
                    <span
                      className={`absolute left-0 top-1/2 -translate-y-1/2 w-0.5 rounded-r-full bg-blue-500
                        transition-all duration-[180ms] ease-out
                        ${isActive ? 'h-5 opacity-100' : 'h-0 opacity-0'}`}
                    />
                    <Icon className={`w-4 h-4 flex-shrink-0 transition-colors duration-150
                      ${isActive ? 'text-blue-400' : isChat ? 'text-blue-400 animate-pulse' : 'text-foreground-3 group-hover:text-foreground-2'}`}
                    />
                    <span>{label}</span>
                  </button>
                  {isChat && <div className="hidden lg:block my-2 border-t border-border" />}
                </div>
              );
            })}
          </aside>

          {/* Content Panel */}
          <div
            ref={contentRef}
            key={tab}
            className="flex-1 bg-surface text-foreground p-6 lg:p-8 space-y-6 overflow-y-auto custom-scrollbar min-w-0 animate-settings-panel-in transition-colors duration-250"
          >

            {/* â”€â”€ General tab (Matching ChatGPT Settings layout) â”€â”€ */}
            {tab === 'general' && (
              <>

                <SectionCard title="General Preferences">
                  <SettingRow label="Appearance" desc="Choose how the interface looks. Changes apply instantly across the workspace.">
                    <CustomSelect
                      options={THEME_OPTIONS}
                      value={theme}
                      onChange={(val) => setTheme(val as any)}
                    />
                  </SettingRow>

                  <SettingRow label="Contrast" desc="Adjust contrast levels for optimal readability across screens.">
                    <CustomSelect
                      options={CONTRAST_OPTIONS}
                      value={contrastMode}
                      onChange={(val) => setContrastMode(val as any)}
                    />
                  </SettingRow>

                  <SettingRow label="Accent color" desc="Select your preferred UI accent highlight shade.">
                    <CustomSelect
                      options={ACCENT_OPTIONS}
                      value={accentColor}
                      onChange={(val) => setAccentColor(val as any)}
                    />
                  </SettingRow>

                  <SettingRow label="Font size" desc="Adjust font scale across all text elements in the application.">
                    <CustomSelect
                      options={FONT_SIZE_OPTIONS}
                      value={fontSize}
                      onChange={(val) => setFontSize(val as any)}
                    />
                  </SettingRow>

                  <SettingRow label="Language" desc="Select preferred language for chat responses and UI labels.">
                    <CustomSelect
                      options={LANGUAGE_OPTIONS}
                      value={language}
                      onChange={(val) => setLanguage(val)}
                    />
                  </SettingRow>

                  <SettingRow label="Higher intelligence" desc="openChat can automatically use a higher intelligence setting when you ask a complex question.">
                    <Toggle label="Higher intelligence" checked={higherIntelligence} onChange={setHigherIntelligence} />
                  </SettingRow>

                  <SettingRow label="Enable Dictation" desc="Use speech-to-text dictation in the chat composer.">
                    <Toggle label="Enable Dictation" checked={enableDictation} onChange={setEnableDictation} />
                  </SettingRow>

                  <SettingRow label="Compact layout" desc="Use dense spacing and reduced padding for maximum screen real-estate.">
                    <Toggle label="Compact layout" checked={compactMode} onChange={setCompactMode} />
                  </SettingRow>
                </SectionCard>
              </>
            )}

            {/* ── Data controls tab ── */}
            {tab === 'datacontrols' && (
              <div className="space-y-4">
                <SectionCard title="Privacy">
                  <SettingRow
                    label="Improve the model for everyone"
                    desc={
                      improveModel
                        ? 'Active: Anonymous chat telemetry enabled to optimize model quality & accuracy.'
                        : 'Disabled: No chat telemetry or conversation data will be shared.'
                    }
                  >
                    <Toggle
                      label="Improve the model"
                      checked={improveModel}
                      onChange={toggleImproveModel}
                    />
                  </SettingRow>

                  <SettingRow
                    label="Location"
                    desc={
                      locationLoading
                        ? 'Detecting your device location...'
                        : locationEnabled && userLocation
                        ? `Active context: ${userLocation}`
                        : 'Allow openChat to use your device\'s location context when providing local responses.'
                    }
                  >
                    <div className="flex items-center gap-2.5">
                      {locationLoading && (
                        <div className="flex items-center gap-1 text-[11px] text-blue-400 font-medium">
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Locating...</span>
                        </div>
                      )}
                      <Toggle
                        label="Location context"
                        checked={locationEnabled}
                        onChange={toggleLocationEnabled}
                      />
                    </div>
                  </SettingRow>
                </SectionCard>

                <SectionCard title="Conversations">
                  <SettingRow
                    label="Shared links"
                    desc="Manage public snapshots and shared links created for your conversations."
                  >
                    <button
                      type="button"
                      onClick={() => setShowSharedLinksModal(true)}
                      className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full
                        bg-surface-2 hover:bg-surface-3 border border-border
                        text-xs font-semibold text-foreground
                        transition-all duration-150 active:scale-[0.97] shadow-sm"
                    >
                      <Link2 className="w-3 h-3" />
                      Manage
                    </button>
                  </SettingRow>

                  <SettingRow
                    label="Archived chats"
                    desc="View, restore, or delete conversations you have previously archived."
                  >
                    <button
                      type="button"
                      onClick={() => setShowArchivedChatsModal(true)}
                      className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full
                        bg-surface-2 hover:bg-surface-3 border border-border
                        text-xs font-semibold text-foreground
                        transition-all duration-150 active:scale-[0.97] shadow-sm"
                    >
                      <FolderClosed className="w-3 h-3" />
                      Manage
                    </button>
                  </SettingRow>

                  <SettingRow
                    label="Archive all chats"
                    desc="Move all current active conversations into archived chats."
                  >
                    <button
                      type="button"
                      onClick={handleArchiveAllChats}
                      className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full
                        bg-surface-2 hover:bg-surface-3 border border-border
                        text-xs font-semibold text-foreground
                        transition-all duration-150 active:scale-[0.97] shadow-sm"
                    >
                      <Archive className="w-3 h-3" />
                      Archive all
                    </button>
                  </SettingRow>
                </SectionCard>
              </div>
            )}

            {/* â”€â”€ AI Models tab â”€â”€ */}
            {tab === 'models' && (
              <div className="flex flex-col xl:flex-row gap-6 h-full items-stretch">

                {/* Models selector */}
                <div className="w-full xl:w-[320px] bg-background rounded-2xl border border-border p-4 flex flex-col max-h-[580px] overflow-hidden flex-shrink-0">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-foreground-3 mb-3 flex items-center gap-1.5">
                    <Cpu className="w-3.5 h-3.5 text-foreground-3" />
                    Available Models
                  </h3>
                  <div className="flex-1 overflow-y-auto pr-1 space-y-2">
                    {availableModelsList.length === 0 ? (
                      <div className="text-center py-8 px-4 text-foreground-3 text-xs leading-relaxed border border-dashed border-border rounded-xl bg-background">
                        No models configured. Enter an API key on the right and click "Verify &amp; Save" to retrieve models.
                      </div>
                    ) : (
                      availableModelsList.map((m) => {
                        const isVerified = verifiedProviderIds.has(m.apiProvider);
                        const isActive   = activeModel === m.id && isVerified;
                        return (
                          <button
                            key={m.id}
                            onClick={() => isVerified ? setActiveModel(m.id) : handleFocusProviderKey(m.apiProvider)}
                            className={`w-full flex items-center justify-between p-2.5 rounded-lg text-left transition-all duration-150
                              ${isActive
                                ? 'bg-surface-2 text-foreground shadow ring-1 ring-blue-500/40'
                                : isVerified
                                ? 'text-foreground-2 hover:bg-surface-3/50 hover:text-foreground cursor-pointer'
                                : 'text-foreground-3 hover:bg-surface-3/30 opacity-75 cursor-pointer'
                              }`}
                          >
                            <div className="flex items-center gap-2.5 min-w-0">
                              {isActive
                                ? <Check className="w-3.5 h-3.5 flex-shrink-0 text-blue-400" />
                                : <div className="w-3.5 h-3.5 flex-shrink-0" />
                              }
                              <div className="truncate">
                                <p className="text-xs font-semibold truncate leading-tight">{m.label}</p>
                                <p className="text-[9px] text-foreground-3 truncate">{m.provider}</p>
                              </div>
                            </div>
                            {isActive ? (
                              <span className="bg-blue-950/40 border border-blue-700/50 text-blue-300 px-1.5 py-0.5 rounded text-[8px] font-bold flex items-center gap-0.5 flex-shrink-0">
                                <span className="w-1 h-1 rounded-full bg-blue-400" />Active
                              </span>
                            ) : isVerified ? (
                              <span className="bg-emerald-500/10 border border-emerald-900/60 text-emerald-400 px-1.5 py-0.5 rounded text-[8px] font-bold flex items-center gap-0.5 flex-shrink-0">
                                <span className="w-1 h-1 rounded-full bg-emerald-400" />Ready
                              </span>
                            ) : (
                              <span className="bg-surface-3 border border-border text-foreground-3 px-1.5 py-0.5 rounded text-[8px] font-bold flex items-center gap-0.5 flex-shrink-0">
                                <span className="w-1 h-1 rounded-full bg-foreground-3" />Unavailable
                              </span>
                            )}
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* Provider key config */}
                <div className="flex-1 flex flex-col min-w-0 max-h-[580px] overflow-hidden">
                  <div className="flex-1 overflow-y-auto pr-1">
                    <div className="space-y-6">
                      <div>
                        <h2 className="text-base font-bold text-foreground flex items-center gap-2">
                          <Key className="w-4 h-4 text-blue-400" />
                          User Keys
                        </h2>
                        <p className="text-xs text-foreground-2 mt-1 leading-relaxed">
                          Use your own LLM tokens by connecting 3rd-party API keys on openChat.
                        </p>
                      </div>

                      <div className="h-px bg-border" />

                      {keysLoading && providers.length === 0 ? (
                        <div className="text-xs text-foreground-3 py-6 text-center flex items-center justify-center gap-2">
                          <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                          Loading API keys configuration...
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {providers.filter((p) => !SEARCH_PROVIDER_IDS.includes(p.id)).map((prov) => {
                            const meta       = PROVIDER_METADATA[prov.id] || { name: prov.id, desc: 'API Provider' };
                            const isVerified = prov.status === 'VERIFIED';
                            const isToggled  = editModes[prov.id] !== undefined ? editModes[prov.id] : (isVerified || prov.saved);
                            return (
                              <div
                                key={prov.id}
                                ref={(el) => { providerCardRefs.current[prov.id] = el; }}
                                className={`p-4 rounded-2xl border transition-all duration-200 bg-background
                                  ${isToggled ? 'border-border shadow-lg shadow-black/10' : 'border-border/60 hover:border-border'}`}
                              >
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2.5 min-w-0">
                                    <p className="text-sm font-semibold text-foreground">{meta.name}</p>
                                    {isVerified && (
                                      <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full text-[10px] font-bold">
                                        Verified
                                      </span>
                                    )}
                                    {prov.saved && isVerified && (
                                      <span className="bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2 py-0.5 rounded-full text-[10px] font-bold">
                                        Saved
                                      </span>
                                    )}
                                  </div>
                                  <Toggle
                                    label={`Toggle ${meta.name} API key`}
                                    checked={isToggled}
                                    onChange={(active) => handleToggleProvider(prov.id, active)}
                                  />
                                </div>
                                {isToggled && (
                                  <ApiKeyField
                                    provider={prov.id}
                                    status={prov.status}
                                    lastError={prov.lastError || null}
                                    initialMaskedKey={prov.saved ? 'â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢' : ''}
                                    onSaveSuccess={(updated) => {
                                      setProviders(providers.map((p) => p.id === prov.id ? updated : p));
                                    }}
                                    onDeleteSuccess={async () => {
                                      const refreshed = await apiRequest('/providers');
                                      setProviders(refreshed);
                                      setEditModes((prev) => ({ ...prev, [prov.id]: false }));
                                    }}
                                  />
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* ── Web Search Providers ───────────────────────────── */}
                      <div className="pt-2">
                        <div className="flex items-center justify-between mb-1">
                          <h2 className="text-base font-bold text-foreground flex items-center gap-2">
                            <Globe className="w-4 h-4 text-violet-400" />
                            Web Search Providers
                          </h2>
                          <span className="text-[9px] font-semibold text-foreground-3 bg-surface-3 border border-border px-2 py-0.5 rounded-full tracking-wide uppercase">
                            Waterfall: Tavily → SerpAPI → Exa → DDG
                          </span>
                        </div>
                        <p className="text-xs text-foreground-2 mb-3 leading-relaxed">
                          Keys are tried in priority order — first available provider is used. DuckDuckGo is always the free fallback (no key needed).
                        </p>

                        <div className="space-y-3">
                          {providers
                            .filter((p) => SEARCH_PROVIDER_IDS.includes(p.id))
                            .map((prov) => {
                              const sMeta = SEARCH_PROVIDER_METADATA[prov.id];
                              if (!sMeta) return null;
                              const isVerified = prov.status === 'VERIFIED';
                              const isToggled  = editModes[prov.id] !== undefined ? editModes[prov.id] : (isVerified || prov.saved);
                              const priority   = SEARCH_PROVIDER_IDS.indexOf(prov.id) + 1;
                              return (
                                <div
                                  key={prov.id}
                                  ref={(el) => { providerCardRefs.current[prov.id] = el; }}
                                  className={`p-4 rounded-2xl border transition-all duration-200 bg-background
                                    ${isToggled ? 'border-violet-900/40 shadow-lg shadow-black/10' : 'border-border/60 hover:border-border'}`}
                                >
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2.5 min-w-0">
                                      <span className="w-5 h-5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-400 text-[9px] font-bold flex items-center justify-center flex-shrink-0">
                                        {priority}
                                      </span>
                                      <p className="text-sm font-semibold text-foreground">{sMeta.name}</p>
                                      {isVerified && (
                                        <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full text-[10px] font-bold">
                                          Active
                                        </span>
                                      )}
                                      {!isVerified && (
                                        <span className="bg-surface-3 text-foreground-3 border border-border px-2 py-0.5 rounded-full text-[10px] font-semibold">
                                          {prov.status === 'INVALID' ? 'Invalid Key' : 'Not Configured'}
                                        </span>
                                      )}
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <a
                                        href={sMeta.docsUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-[10px] text-violet-400 hover:text-violet-300 transition-colors flex items-center gap-0.5"
                                        title={`Get ${sMeta.name} API key`}
                                      >
                                        <Link2 className="w-3 h-3" />
                                        Get key
                                      </a>
                                      <Toggle
                                        label={`Toggle ${sMeta.name} API key`}
                                        checked={isToggled}
                                        onChange={(active) => handleToggleProvider(prov.id, active)}
                                      />
                                    </div>
                                  </div>
                                  <p className="text-[11px] text-foreground-3 mt-1 mb-0 leading-snug">{sMeta.desc}</p>
                                  {isToggled && (
                                    <ApiKeyField
                                      provider={prov.id}
                                      status={prov.status}
                                      lastError={prov.lastError || null}
                                      initialMaskedKey={prov.saved ? '••••••••••••••••' : ''}
                                      onSaveSuccess={(updated) => {
                                        setProviders(providers.map((p) => p.id === prov.id ? updated : p));
                                      }}
                                      onDeleteSuccess={async () => {
                                        const refreshed = await apiRequest('/providers');
                                        setProviders(refreshed);
                                        setEditModes((prev) => ({ ...prev, [prov.id]: false }));
                                      }}
                                    />
                                  )}
                                </div>
                              );
                            })}
                        </div>
                      </div>

                      <div className="flex items-start gap-3 p-3.5 rounded-2xl border border-border bg-background text-[11px] text-foreground-2">
                        <Shield className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                        <span>Keys are verified against the provider API before storage. They are <strong>AES-encrypted</strong> at rest in the database and never exposed in logs or API responses.</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* â”€â”€ Generation tab â”€â”€ */}
            {tab === 'generation' && (
              <SectionCard title="Generation Parameters">
                <SettingRow
                  label="Temperature"
                  desc={`Controls randomness. Lower = more focused, higher = more creative. Current: ${temperature}`}
                >
                  <div className="flex items-center gap-2 text-foreground">
                    <span className="text-xs text-foreground-3 w-5 text-right">0</span>
                    <input
                      type="range" min="0" max="1" step="0.05"
                      value={temperature}
                      onChange={(e) => setTemperatureState(parseFloat(e.target.value))}
                      className="w-28 h-1.5 bg-surface-3 rounded-lg appearance-none cursor-pointer accent-blue-600"
                    />
                    <span className="text-xs text-foreground-3 w-5">1</span>
                    <span className="text-xs font-mono font-bold text-foreground w-8 text-right">{temperature}</span>
                  </div>
                </SettingRow>

                <SettingRow label="Max Output Tokens" desc="Maximum number of tokens in the response.">
                  <input
                    type="number"
                    value={maxTokens}
                    onChange={(e) => setMaxTokensState(Math.max(256, Math.min(8192, parseInt(e.target.value) || 2048)))}
                    min={256} max={8192} step={256}
                    className="w-24 bg-background border border-border rounded-lg px-2 py-1.5 text-xs text-foreground text-right focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 shadow-inner font-semibold"
                  />
                </SettingRow>

                <SettingRow label="Streaming Responses" desc="Show responses as they are generated token by token.">
                  <Toggle label="Streaming responses" checked={streaming} onChange={setStreamingState} />
                </SettingRow>

                <div className="py-3 flex justify-end">
                  <button
                    onClick={handleSaveGeneration}
                    className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition-all duration-150 border shadow-sm
                      ${saved
                        ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-400'
                        : 'bg-surface-3 border-border text-foreground hover:bg-surface-2'}`}
                  >
                    {saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
                    {saved ? 'Saved!' : 'Save Changes'}
                  </button>
                </div>
              </SectionCard>
            )}

            {/* â”€â”€ Features tab â”€â”€ */}
            {tab === 'features' && (
              <SectionCard title="AI Feature Flags">
                <SettingRow label="Semantic Memory" desc="Automatically extract and recall long-term facts about you.">
                  <Toggle label="Semantic Memory" checked={memoryEnabled} onChange={setMemoryEnabled} />
                </SettingRow>
                <SettingRow label="RAG (Document Q&A)" desc="Use uploaded documents as context for responses.">
                  <Toggle label="RAG Document Q&A" checked={ragEnabled} onChange={setRagEnabled} />
                </SettingRow>
                <SettingRow label="Tool Calling" desc="Allow the AI to execute functions and external tools.">
                  <Toggle label="Tool Calling" checked={toolsEnabled} onChange={setToolsEnabled} />
                </SettingRow>
                <SettingRow label="Web Search" desc="Enable real-time web search via Tavily.">
                  <Toggle label="Web Search" checked={webEnabled} onChange={setWebEnabled} />
                </SettingRow>
                <SettingRow label="Developer HUD" desc="Show execution telemetry alongside chat messages.">
                  <Toggle
                    label="Developer HUD"
                    checked={developerMode}
                    onChange={(v) => { if (v !== developerMode) toggleDeveloperMode(); }}
                  />
                </SettingRow>
              </SectionCard>
            )}

            {/* â”€â”€ Documents tab â”€â”€ */}
            {tab === 'documents' && (
              <div className="settings-section space-y-6 animate-fade-in">
                <div>
                  <h2 className="text-base font-bold text-foreground flex items-center gap-2">
                    <FolderClosed className="w-4 h-4 text-blue-400" />
                    Agent Documents Ingestion
                  </h2>
                  <p className="text-xs text-foreground-2 mt-1 leading-relaxed">
                    Upload documents to populate the vector store. The agent retrieves knowledge from these files for context-aware Q&amp;A.
                  </p>
                </div>

                <div className="h-px bg-border" />

                <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                  {/* Upload column */}
                  <div className="space-y-4">
                    <div className="p-5 rounded-2xl border border-border bg-background space-y-4">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-foreground-3 flex items-center gap-2">
                        <UploadCloud className="w-4 h-4 text-blue-500" />
                        <span>Ingest Document</span>
                      </h3>
                      <p className="text-foreground-2 text-[10px] leading-relaxed">
                        Upload PDF, TXT, DOCX, or Excel sheets. openChat parses, chunks, embeds, and indexes the content into the vector store automatically.
                      </p>

                      <label className={`w-full flex flex-col items-center justify-center border-2 border-dashed rounded-xl p-6 cursor-pointer transition-all duration-150
                        ${uploading
                          ? 'border-blue-500/40 bg-blue-500/5 cursor-not-allowed'
                          : 'border-border hover:border-blue-500/40 hover:bg-blue-500/5'}`}>
                        <UploadCloud className={`w-7 h-7 mb-2 ${uploading ? 'text-blue-400 animate-pulse' : 'text-foreground-3'}`} />
                        <span className="text-[10px] font-semibold text-foreground">
                          {uploading ? 'Processing...' : 'Click to select a file'}
                        </span>
                        <span className="text-[9px] text-foreground-3 mt-1">PDF, DOCX, TXT, XLSX â€” up to 20 MB</span>
                        <input
                          type="file"
                          className="hidden"
                          onChange={handleFileUpload}
                          disabled={uploading}
                          accept=".pdf,.docx,.xlsx,.xls,.pptx,.txt,.md,.csv,.json"
                        />
                      </label>

                      {(ingestStep >= 0 || uploadError) && (
                        <IngestionProgress
                          filename={ingestFilename}
                          currentStep={ingestStep}
                          done={ingestDone}
                          error={uploadError}
                        />
                      )}
                    </div>
                    <PipelineExplainer />
                  </div>

                  {/* Document list column */}
                  <div className="xl:col-span-2 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-foreground-3">Active Vector Store Files</h3>
                      <span className="text-[10px] text-foreground-3 font-medium">{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
                    </div>

                    <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
                      {documents.map((doc) => (
                        <div
                          key={doc.id}
                          className="p-4 rounded-xl border border-border bg-surface flex items-center justify-between shadow-sm shadow-black/10 hover:border-blue-500/30 transition-all duration-150"
                        >
                          <div className="flex items-center gap-3.5 min-w-0">
                            <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex-shrink-0">
                              {doc.file_type.includes('code') ? <FileCode className="w-4 h-4" /> : <FileText className="w-4 h-4" />}
                            </div>
                            <div className="min-w-0">
                              <p className="text-xs font-semibold truncate text-foreground">{doc.filename}</p>
                              <p className="text-[10px] text-foreground-3 mt-0.5">
                                {(doc.size_bytes / 1024).toFixed(1)} KB &bull; Ingested {new Date(doc.uploaded_at).toLocaleDateString()}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-3 flex-shrink-0">
                            {doc.status === 'ready' && (
                              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                <CheckCircle2 className="w-2.5 h-2.5" />Vectorized
                              </span>
                            )}
                            {doc.status === 'processing' && (
                              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                                <Loader2 className="w-2.5 h-2.5 animate-spin" />Indexing
                              </span>
                            )}
                            {doc.status === 'failed' && (
                              <Tooltip content={doc.error_message || 'Document indexing failed. Check server logs.'} side="top">
                                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20 cursor-help">
                                  <XCircle className="w-2.5 h-2.5" />Failed
                                </span>
                              </Tooltip>
                            )}
                            <Tooltip content="Delete document" side="top">
                              <button
                                onClick={() => handleDeleteDoc(doc.id)}
                                className="p-1.5 rounded-lg border border-border bg-surface-2 text-foreground-3 hover:text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/20 transition-all duration-150"
                                aria-label="Delete document"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </Tooltip>
                          </div>
                        </div>
                      ))}

                      {documents.length === 0 && (
                        <div className="text-center py-16 border border-dashed border-border rounded-2xl bg-background text-foreground-3">
                          <FolderClosed className="w-8 h-8 mx-auto mb-3 text-foreground-3 opacity-40" />
                          <p className="text-xs font-medium">No documents uploaded yet</p>
                          <p className="text-[10px] mt-1 text-foreground-3 font-medium">RAG will not activate until at least one document is indexed.</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* â”€â”€ Memories tab â”€â”€ */}
            {tab === 'memories' && (
              <div className="settings-section space-y-6 animate-fade-in">
                <div>
                  <h2 className="text-base font-bold text-foreground flex items-center gap-2">
                    <Brain className="w-4 h-4 text-blue-400" />
                    Agent Episodic Fact Memory
                  </h2>
                  <p className="text-xs text-foreground-2 mt-1 leading-relaxed">
                    View and manage long-term facts the AI has extracted about you, or manually record core facts and preferences.
                  </p>
                </div>

                <div className="h-px bg-border" />

                <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                  {/* Record form */}
                  <form onSubmit={handleAddMemory} className="p-5 rounded-2xl border border-border bg-background space-y-4 h-fit">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-foreground-3 flex items-center gap-2">
                      <Brain className="w-4 h-4 text-blue-500" />
                      <span>Record Fact</span>
                    </h3>

                    <div className="space-y-1.5">
                      <label className="text-[10px] font-semibold text-foreground-2 block">Category</label>
                      <CustomSelect
                        options={MEMORY_CATEGORY_OPTIONS}
                        value={memCategory}
                        onChange={(val) => setMemCategory(val as any)}
                        align="left"
                        className="w-full"
                        buttonClassName="w-full justify-between"
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-[10px] font-semibold text-foreground-2 block">Fact Content</label>
                      <textarea
                        value={memContent}
                        onChange={(e) => setMemContent(e.target.value)}
                        placeholder="User prefers Python over JS for scripting..."
                        rows={3}
                        required
                        className="w-full rounded-xl py-2 px-3 text-xs bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all duration-150 resize-none"
                      />
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between text-[10px] font-semibold text-foreground-2">
                        <span>Importance Score</span>
                        <span className="text-blue-400 font-bold">{memImportance}/10</span>
                      </div>
                      <input
                        type="range"
                        min="1" max="10"
                        value={memImportance}
                        onChange={(e) => setMemImportance(Number(e.target.value))}
                        className="w-full h-1.5 rounded-lg appearance-none cursor-pointer accent-blue-600 bg-surface-3"
                      />
                    </div>

                    <button
                      type="submit"
                      className="w-full flex items-center justify-center gap-2 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-all duration-150 shadow-md active:scale-[0.98]"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Save Fact</span>
                    </button>

                    {memError && (
                      <div className="flex items-center gap-1.5 p-3 rounded-xl border border-rose-500/20 bg-rose-500/5 text-rose-400 text-[10px]">
                        <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                        <span>{memError}</span>
                      </div>
                    )}
                  </form>

                  {/* Memory list */}
                  <div className="xl:col-span-2 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-foreground-3">Long-Term Memory Registry</h3>
                      <span className="text-[10px] text-foreground-3 font-medium">{memories.length} entr{memories.length !== 1 ? 'ies' : 'y'}</span>
                    </div>

                    <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
                      {memories.map((m) => (
                        <div
                          key={m.id}
                          className="p-4 rounded-2xl border border-border bg-background flex items-start justify-between shadow-sm hover:border-border/80 transition-all duration-150"
                        >
                          <div className="space-y-1.5 min-w-0 pr-4">
                            <div className="flex items-center gap-2.5">
                              <span className={`inline-block px-2 py-0.5 rounded-full text-[9px] font-semibold capitalize ${
                                m.category === 'preference' ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20' :
                                m.category === 'goal'       ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                                m.category === 'topic'      ? 'bg-pink-500/10 text-pink-400 border border-pink-500/20' :
                                'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                              }`}>
                                {m.category}
                              </span>
                              <span className="flex items-center gap-1 text-[9px] text-foreground-3 font-medium">
                                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                                <span>Importance: {m.importance_score}/10</span>
                              </span>
                            </div>
                            <p className="text-xs leading-relaxed text-foreground-2">{m.content}</p>
                            <p className="text-[9px] text-foreground-3 flex items-center gap-1">
                              <Calendar className="w-3.5 h-3.5" />
                              <span>Synthesized {new Date(m.created_at).toLocaleDateString()}</span>
                            </p>
                          </div>
                          <Tooltip content="Delete memory" side="top">
                            <button
                              onClick={() => handleDeleteMemory(m.id)}
                              className="p-1.5 rounded-lg border border-border bg-surface-2 text-foreground-3 hover:text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/20 transition-all duration-150 flex-shrink-0"
                              aria-label="Delete memory"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </Tooltip>
                        </div>
                      ))}

                      {memories.length === 0 && (
                        <div className="text-center py-16 border border-dashed border-border rounded-2xl bg-background text-foreground-3">
                          <Brain className="w-8 h-8 mx-auto mb-3 text-foreground-3 opacity-40" />
                          <p className="text-xs font-medium">No long-term memories yet</p>
                          <p className="text-[10px] mt-1 text-foreground-3 font-medium">Let the agent parse user context to auto-extract facts.</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}



            {/* ── Remote MCP Servers tab ── */}
            {tab === 'mcpservers' && (
              <div className="space-y-6">
                <SectionCard title="Remote MCP Server Integration">
                  <div className="p-4 rounded-xl bg-surface-2 border border-border/60 space-y-2">
                    <div className="flex items-center gap-2 text-primary font-semibold text-sm">
                      <Sparkles className="w-4 h-4" />
                      <span>Deploy & Connect Custom Tools</span>
                    </div>
                    <p className="text-xs text-foreground-3 leading-relaxed">
                      Connect your deployed Model Context Protocol (MCP) servers by providing their HTTP or SSE endpoint URL.
                      The agent performs automatic tool discovery on startup, registers available functions, and routes chat tool calls directly to your remote server.
                    </p>
                  </div>
                </SectionCard>

                <SectionCard title="Add Remote MCP Server">
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-foreground-2 mb-1">Server Name *</label>
                        <input
                          type="text"
                          value={mcpName}
                          onChange={(e) => setMcpName(e.target.value)}
                          placeholder="e.g. My Custom Weather Tool"
                          className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-xs focus:ring-2 focus:ring-primary/50 outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-foreground-2 mb-1">Server Endpoint URL *</label>
                        <input
                          type="url"
                          value={mcpUrl}
                          onChange={(e) => setMcpUrl(e.target.value)}
                          placeholder="https://my-mcp-tool.vercel.app/mcp"
                          className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-xs focus:ring-2 focus:ring-primary/50 outline-none"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-foreground-2 mb-1">Authorization Header / Token (Optional)</label>
                        <input
                          type="password"
                          value={mcpAuth}
                          onChange={(e) => setMcpAuth(e.target.value)}
                          placeholder="Bearer secret-token or API key"
                          className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-xs focus:ring-2 focus:ring-primary/50 outline-none"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-foreground-2 mb-1">Transport Protocol</label>
                        <select
                          value={mcpTransport}
                          onChange={(e) => setMcpTransport(e.target.value)}
                          className="w-full px-3 py-2 rounded-xl border border-border bg-background text-foreground text-xs focus:ring-2 focus:ring-primary/50 outline-none"
                        >
                          <option value="http_jsonrpc">HTTP POST (JSON-RPC 2.0)</option>
                          <option value="http_sse">Server-Sent Events (SSE / Stream)</option>
                        </select>
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-3 pt-2">
                      <button
                        type="button"
                        onClick={handleTestMcpConnection}
                        disabled={isTestingMcp}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-border bg-surface-2 hover:bg-surface-3 text-foreground text-xs font-semibold disabled:opacity-50 transition-all cursor-pointer active:scale-95"
                      >
                        {isTestingMcp ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 text-primary" />}
                        <span>Test Connection</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleAddMcpServer}
                        disabled={isSavingMcp}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold hover:brightness-110 disabled:opacity-50 transition-all shadow-sm cursor-pointer active:scale-95"
                      >
                        {isSavingMcp ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                        <span>Save & Register Server</span>
                      </button>
                    </div>


                    {/* Test result card */}
                    {mcpTestResult && (
                      <div className={`p-4 rounded-xl border text-xs space-y-2 ${mcpTestResult.status === 'success' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-rose-500/10 border-rose-500/30 text-rose-400'}`}>
                        <div className="flex items-center justify-between font-bold">
                          <div className="flex items-center gap-2">
                            {mcpTestResult.status === 'success' ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                            <span>{mcpTestResult.status === 'success' ? 'Connection Successful' : 'Connection Failed'}</span>
                          </div>
                          <span className="text-[11px] opacity-80">{mcpTestResult.latency_ms}ms latency</span>
                        </div>
                        <p className="text-[11px] opacity-90">{mcpTestResult.message}</p>
                        
                        {mcpTestResult.tools && mcpTestResult.tools.length > 0 && (
                          <div className="pt-2">
                            <span className="font-semibold block mb-1">Exposed Tools ({mcpTestResult.tools.length}):</span>
                            <div className="flex flex-wrap gap-1.5">
                              {mcpTestResult.tools.map((t: any) => (
                                <span key={t.name} className="px-2 py-1 rounded-md bg-emerald-500/20 text-emerald-300 font-mono text-[10px] border border-emerald-500/30">
                                  ⚡ {t.name}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </SectionCard>

                <SectionCard title="Configured Remote MCP Servers">
                  {isLoadingMcp ? (
                    <div className="flex items-center justify-center py-10 text-foreground-3 text-xs gap-2">
                      <Loader2 className="w-4 h-4 animate-spin text-primary" />
                      <span>Loading MCP servers...</span>
                    </div>
                  ) : mcpServers.length === 0 ? (
                    <div className="text-center py-12 border border-dashed border-border rounded-2xl bg-background text-foreground-3">
                      <Link2 className="w-8 h-8 mx-auto mb-2 text-foreground-3 opacity-40" />
                      <p className="text-xs font-semibold">No Remote MCP Servers Connected</p>
                      <p className="text-[11px] text-foreground-3 mt-1">Paste your deployed MCP server endpoint URL above to register custom tools.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {mcpServers.map((srv) => (
                        <div key={srv.id} className="p-4 rounded-xl border border-border bg-background hover:border-border/80 transition-all">
                          <div className="flex items-start justify-between gap-4">
                            <div className="space-y-1">
                              <div className="flex items-center gap-2">
                                <h4 className="text-xs font-bold text-foreground">{srv.name}</h4>
                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${srv.is_enabled ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' : 'bg-zinc-500/15 text-zinc-400 border border-zinc-500/30'}`}>
                                  {srv.is_enabled ? 'Active' : 'Disabled'}
                                </span>
                              </div>
                              <p className="text-[11px] font-mono text-foreground-3 break-all">{srv.url}</p>
                            </div>

                            <div className="flex items-center gap-2">
                              {/* Toggle switch */}
                              <button
                                type="button"
                                onClick={() => handleToggleMcpServer(srv.id, srv.is_enabled)}
                                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${srv.is_enabled ? 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20' : 'bg-surface-2 text-foreground-3 hover:bg-surface-3'}`}
                              >
                                {srv.is_enabled ? 'Disable' : 'Enable'}
                              </button>

                              {/* Delete button */}
                              <button
                                type="button"
                                onClick={() => handleDeleteMcpServer(srv.id)}
                                className="p-1.5 rounded-lg border border-border bg-surface-2 text-foreground-3 hover:text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/20 transition-all"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>

                          {srv.discovered_tools && srv.discovered_tools.length > 0 && (
                            <div className="mt-3 pt-3 border-t border-border/60">
                              <span className="text-[10px] font-semibold text-foreground-3 block mb-1.5">Exposed Tools ({srv.discovered_tools.length}):</span>
                              <div className="flex flex-wrap gap-1.5">
                                {srv.discovered_tools.map((t) => (
                                  <div key={t.name} className="px-2 py-1 rounded-md bg-surface-2 border border-border text-[11px] flex items-center gap-1.5">
                                    <span className="font-mono text-primary font-bold text-[10px]">⚡ {t.name}</span>
                                    {t.description && <span className="text-foreground-3 text-[10px] max-w-[200px] truncate">— {t.description}</span>}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </SectionCard>
              </div>
            )}



            {/* ── Account tab ── */}
            {tab === 'account' && (

              <>
                <SectionCard title="Profile">
                  <SettingRow label="Name" desc={user?.full_name || 'Not set'}>
                    <span className="text-xs text-foreground-2 font-semibold">{user?.email}</span>
                  </SettingRow>
                </SectionCard>

                <SectionCard title="Data Management">
                  <SettingRow label="Export Workspace Data" desc="Download all your chat history as a JSON file.">
                    <button
                      onClick={handleExportData}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border bg-background hover:bg-surface-2 text-foreground text-xs font-bold transition-all duration-150 shadow-sm active:scale-[0.98]"
                    >
                      <Download className="w-3.5 h-3.5 text-foreground-3" />
                      <span>Export Data</span>
                    </button>
                  </SettingRow>

                  <SettingRow label="Delete All Conversations" desc="Permanently remove all chat history. This action is irreversible." danger>
                    <button
                      onClick={handleDeleteConversations}
                      className={`flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-bold transition-all duration-150 shadow-sm active:scale-[0.98]
                        ${deleteConfirm
                          ? 'bg-rose-955/20 border-rose-800/40 text-rose-400 hover:bg-rose-955/30'
                          : 'bg-background border-border text-rose-400 hover:bg-surface-2'}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>{deleteConfirm ? 'Confirm Delete' : 'Delete All'}</span>
                    </button>
                  </SettingRow>
                </SectionCard>

                <SectionCard title="Session">
                  <SettingRow label="Sign Out" desc="Log out of your current workspace session." danger>
                    <button
                      onClick={handleLogout}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-rose-900/30 bg-rose-955/10 hover:bg-rose-955/25 text-rose-400 text-xs font-bold transition-all duration-150 shadow-sm active:scale-[0.98]"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      <span>Logout</span>
                    </button>
                  </SettingRow>
                </SectionCard>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Shared Links Modal */}
      {showSharedLinksModal && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
          onClick={(e) => { if (e.target === e.currentTarget) setShowSharedLinksModal(false); }}
        >
          <div className="bg-surface border border-border rounded-2xl max-w-md w-full shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-surface-2/40">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                  <Link2 className="w-3.5 h-3.5 text-blue-400" />
                </div>
                <h3 className="font-bold text-sm text-foreground">Shared Links</h3>
              </div>
              <button
                onClick={() => setShowSharedLinksModal(false)}
                className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-colors"
              >
                <XCircle className="w-4 h-4" />
              </button>
            </div>
            {/* Body */}
            <div className="p-5 space-y-2 max-h-72 overflow-y-auto">
              {chats.filter(c => c.title?.includes('[Shared]') || localStorage.getItem(`shared_link_${c.id}`)).length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8">
                  <Globe className="w-8 h-8 text-foreground-3/40" />
                  <p className="text-xs text-foreground-3 italic">No active shared public links found.</p>
                </div>
              ) : (
                chats
                  .filter(c => c.title?.includes('[Shared]') || localStorage.getItem(`shared_link_${c.id}`))
                  .map((c) => (
                    <div key={c.id} className="flex items-center justify-between p-3 rounded-xl bg-surface-2 border border-border hover:border-border-2 transition-colors">
                      <div className="flex items-center gap-2 min-w-0 flex-1 pr-2">
                        <Link2 className="w-3 h-3 text-foreground-3 flex-shrink-0" />
                        <span className="text-xs text-foreground font-medium truncate">{c.title || 'Untitled Snapshot'}</span>
                      </div>
                      <button
                        onClick={() => {
                          localStorage.removeItem(`shared_link_${c.id}`);
                          addToast('Shared link revoked.', 'success');
                        }}
                        className="inline-flex items-center gap-1 text-[11px] text-rose-400 hover:text-rose-300
                          font-semibold px-2.5 py-1 rounded-lg hover:bg-rose-950/20
                          border border-transparent hover:border-rose-900/30 transition-all flex-shrink-0"
                      >
                        <XCircle className="w-3 h-3" /> Revoke
                      </button>
                    </div>
                  ))
              )}
            </div>
            {/* Footer */}
            <div className="flex justify-end px-5 py-3 border-t border-border bg-surface-2/20">
              <button
                onClick={() => setShowSharedLinksModal(false)}
                className="px-4 py-1.5 rounded-lg bg-surface-2 hover:bg-surface-3 border border-border
                  text-foreground text-xs font-semibold transition-all active:scale-[0.97]"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Archived Chats Modal */}
      {showArchivedChatsModal && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
          onClick={(e) => { if (e.target === e.currentTarget) setShowArchivedChatsModal(false); }}
        >
          <div className="bg-surface border border-border rounded-2xl max-w-md w-full shadow-2xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-surface-2/40">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                  <Archive className="w-3.5 h-3.5 text-amber-400" />
                </div>
                <h3 className="font-bold text-sm text-foreground">
                  Archived Chats
                  {archivedChatsList.length > 0 && (
                    <span className="ml-2 bg-surface-3 text-foreground-2 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                      {archivedChatsList.length}
                    </span>
                  )}
                </h3>
              </div>
              <button
                onClick={() => setShowArchivedChatsModal(false)}
                className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-colors"
              >
                <XCircle className="w-4 h-4" />
              </button>
            </div>
            {/* Body */}
            <div className="p-5 space-y-2 max-h-72 overflow-y-auto">
              {archivedChatsList.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8">
                  <Archive className="w-8 h-8 text-foreground-3/40" />
                  <p className="text-xs text-foreground-3 italic">No archived conversations.</p>
                </div>
              ) : (
                archivedChatsList.map((c: any) => (
                  <div key={c.id} className="flex items-center justify-between p-3 rounded-xl bg-surface-2 border border-border hover:border-border-2 transition-colors">
                    <div className="flex items-center gap-2 min-w-0 flex-1 pr-2">
                      <FolderClosed className="w-3 h-3 text-foreground-3 flex-shrink-0" />
                      <span className="text-xs text-foreground font-medium truncate">{c.title || 'Untitled Chat'}</span>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <button
                        onClick={() => handleUnarchiveChat(c.id)}
                        className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300
                          font-semibold px-2.5 py-1 rounded-lg hover:bg-blue-950/20
                          border border-transparent hover:border-blue-900/30 transition-all"
                      >
                        <RotateCcw className="w-3 h-3" /> Unarchive
                      </button>
                      <button
                        onClick={() => handleDeleteArchivedChat(c.id)}
                        className="inline-flex items-center gap-1 text-[11px] text-rose-400 hover:text-rose-300
                          font-semibold px-2.5 py-1 rounded-lg hover:bg-rose-950/20
                          border border-transparent hover:border-rose-900/30 transition-all"
                      >
                        <Trash2 className="w-3 h-3" /> Delete
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
            {/* Footer */}
            <div className="flex justify-end px-5 py-3 border-t border-border bg-surface-2/20">
              <button
                onClick={() => setShowArchivedChatsModal(false)}
                className="px-4 py-1.5 rounded-lg bg-surface-2 hover:bg-surface-3 border border-border
                  text-foreground text-xs font-semibold transition-all active:scale-[0.97]"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete All Chats Confirmation Modal — kept for internal use */}
    </div>
  );
}
