import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useChatStore } from '../store/chatStore';
import { useUIStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { apiRequest } from '../services/api';
import { ProviderKeyManager } from '../services/providerKeyManager';
import Logo from '../components/ui/Logo';
import { Tooltip } from '../components/ui/Tooltip';
import KeyboardShortcutsModal from '../components/ui/KeyboardShortcutsModal';
import GlobalSearch from '../components/ui/GlobalSearch';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import { ChatInput } from '../components/chat/ChatInput';
import { ToastContainer } from '../components/ui/Toast';
import { useToast } from '../hooks/useToast';
import {
  Send, Upload, Plus, Terminal, Database, Lock,
  Sparkles, Cpu, X, CheckCircle2, Copy, Check,
  RefreshCw, ChevronLeft, ChevronRight,
  Search, ArrowDown,
  MessageSquare, Pencil, Trash2, Pin,
  BookOpen, Share2, Download, FileJson, FileText,
  MoreHorizontal, Archive, FolderClosed, ChevronDown, Files,
  Settings, LogOut, ListOrdered, KeyRound, GitBranch, Link
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────
//  Types
// ─────────────────────────────────────────────────────────────
import { SourceDocument } from '../types/chat';

// Helper: Relative time formatter with UTC-safe parsing
// Backend stores naive UTC datetimes without timezone suffix;
// appending 'Z' prevents browsers from mis-interpreting them as local time.
function formatRelativeTime(dateStr?: string) {
  if (!dateStr) return '';
  let s = dateStr.trim();
  // If no timezone info, treat as UTC
  if (!s.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(s)) {
    s = s.replace(' ', 'T');
    if (!s.includes('T')) s += 'T00:00:00Z';
    else s += 'Z';
  }
  const d = new Date(s);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffHours < 48) return 'Yesterday';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// ── Helper: Format Clean Chat Title (ChatGPT Inspired) ───────────
function formatChatTitle(rawTitle?: string): string {
  if (!rawTitle || rawTitle.trim() === '' || rawTitle === 'New Chat') {
    return 'New Chat';
  }

  let cleaned = rawTitle.trim();

  // Custom replacements for known prompt patterns
  if (/^am mannu$/i.test(cleaned) || /^i am /i.test(rawTitle)) {
    return 'Introduction';
  }
  if (/^keys models gemini/i.test(cleaned) || /gemini.*flash/i.test(rawTitle)) {
    return 'Gemini Models';
  }
  if (/explain tcp vs udp/i.test(rawTitle)) {
    return 'TCP vs UDP';
  }
  if (/langgraph memory/i.test(rawTitle)) {
    return 'LangGraph Memory';
  }

  // Strip greetings and common conversational filler prefixes
  cleaned = cleaned.replace(/^(hi|hello|hey|greetings|can you|could you|please|explain everything about|explain|tell me about|what is|how to|i want to|how do i)\s+/i, '');

  // Trim trailing punctuation
  cleaned = cleaned.replace(/[\.\?\!]+$/, '').trim();

  // Limit to 2–5 words max
  const words = cleaned.split(/\s+/).filter(Boolean);
  if (words.length > 5) {
    cleaned = words.slice(0, 4).join(' ');
  }

  if (!cleaned) return rawTitle;

  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

// ── Helper: Group Conversations by Date ──────────────────────────
function groupChatsByDate(chatList: any[]) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;
  const sevenDaysAgo = todayStart - 6 * 86400000;

  const today: any[] = [];
  const yesterday: any[] = [];
  const last7Days: any[] = [];
  const older: any[] = [];

  chatList.forEach((c) => {
    const rawDate = c.updated_at || c.created_at;
    let chatTime = 0;
    if (rawDate) {
      let s = String(rawDate).trim();
      if (!s.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(s)) {
        s = s.replace(' ', 'T');
        if (!s.includes('T')) s += 'T00:00:00Z';
        else s += 'Z';
      }
      chatTime = new Date(s).getTime();
    }

    if (isNaN(chatTime) || chatTime === 0) {
      older.push(c);
    } else if (chatTime >= todayStart) {
      today.push(c);
    } else if (chatTime >= yesterdayStart) {
      yesterday.push(c);
    } else if (chatTime >= sevenDaysAgo) {
      last7Days.push(c);
    } else {
      older.push(c);
    }
  });

  return { today, yesterday, last7Days, older };
}

// ─────────────────────────────────────────────────────────────
//  Word count, reading time & section helpers
// ─────────────────────────────────────────────────────────────
function getResponseMeta(content: string) {
  const words    = content.trim().split(/\s+/).filter(Boolean).length;
  const readSecs = Math.ceil(words / 3.5);
  const mins     = Math.floor(readSecs / 60);
  const secs     = readSecs % 60;
  const readTime = mins >= 1 ? `${mins} min read` : `${secs}s read`;
  const sections = (content.match(/^#{1,4}\s/gm) || []).length;
  return { words, readTime, sections, isLong: words > 250 };
}

function decodeHtmlEntities(str: string): string {
  if (!str) return '';
  return str
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&#039;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>');
}

function parseUserMessageFiles(content: string) {
  let cleanPrompt = decodeHtmlEntities(content);
  let refTitle: string | null = null;

  // Extract and strip connected reference context block if present
  const refContextMatch = cleanPrompt.match(/\[Connected Reference Context from Chat:\s*"([^"]+)"\][\s\S]*?\[End of Referenced Context\]\s*/i);
  if (refContextMatch) {
    refTitle = refContextMatch[1];
    cleanPrompt = cleanPrompt.replace(refContextMatch[0], '');
  }

  const fileRegex = /\[Attached File:\s*([^\]]+)\]\n```[\s\S]*?```/g;
  const files: { name: string; content: string }[] = [];

  let match;
  while ((match = fileRegex.exec(cleanPrompt)) !== null) {
    const fullBlock = match[0];
    const name = match[1];
    const codeMatch = fullBlock.match(/```\n([\s\S]*?)\n```/);
    const fileContent = codeMatch ? codeMatch[1] : '';
    files.push({ name, content: fileContent });
    cleanPrompt = cleanPrompt.replace(fullBlock, '');
  }

  return { prompt: cleanPrompt.trim(), files, refTitle };
}

// ─────────────────────────────────────────────────────────────
//  Markdown code block
// ─────────────────────────────────────────────────────────────
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(code.split('\n').length > 22);

  return (
    <div className={`code-block-wrapper ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="code-block-header">
        <div className="lang-badge">
          <span className={`lang-dot ${language || 'default'}`} />
          <span>{language || 'text'}</span>
        </div>
        <div className="actions">
          <button
            onClick={() => {
              navigator.clipboard.writeText(code).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              });
            }}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
            aria-label="Copy code"
          >
            {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
      </div>
      <SyntaxHighlighter
        style={oneDark}
        language={language || 'text'}
        PreTag="pre"
        showLineNumbers={code.split('\n').length > 4}
        wrapLongLines={false}
        customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.82rem', background: '#0d1117' }}
        codeTagProps={{ style: { fontFamily: "'JetBrains Mono', monospace" } }}
      >
        {code}
      </SyntaxHighlighter>
      {code.split('\n').length > 22 && (
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="code-block-expand-btn"
        >
          {isCollapsed ? 'Expand code block' : 'Collapse code block'}
        </button>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Base Markdown renderer — full component override
// ─────────────────────────────────────────────────────────────
function MarkdownContent({ content, isStreaming }: { content: string; isStreaming?: boolean }) {
  return (
    <div className={`prose-chat ${isStreaming ? 'streaming-cursor' : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Inline & block code
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            if (!match) {
              return (
                <code className="prose-chat-inline-code" {...props}>
                  {children}
                </code>
              );
            }
            return <CodeBlock language={match[1]} code={String(children).replace(/\n$/, '')} />;
          },
          // Tables — wrap in scrollable container
          table({ children }) {
            return (
              <div className="table-wrapper">
                <table>{children}</table>
              </div>
            );
          },
          thead({ children }) { return <thead>{children}</thead>; },
          tbody({ children }) { return <tbody>{children}</tbody>; },
          tr({ children })   { return <tr>{children}</tr>; },
          th({ children, style }) {
            return <th style={style}>{children}</th>;
          },
          td({ children, style }) {
            return <td style={style}>{children}</td>;
          },
          // Headings
          h1({ children }) { return <h1>{children}</h1>; },
          h2({ children }) { return <h2>{children}</h2>; },
          h3({ children }) { return <h3>{children}</h3>; },
          h4({ children }) { return <h4>{children}</h4>; },
          h5({ children }) { return <h5>{children}</h5>; },
          h6({ children }) { return <h6>{children}</h6>; },
          // Paragraph
          p({ children }) { return <p>{children}</p>; },
          // Horizontal rule
          hr() { return <hr />; },
          // Blockquote
          blockquote({ children }) { return <blockquote>{children}</blockquote>; },
          // Links
          a({ href, children }) {
            return (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            );
          },
          // Images
          img({ src, alt }) {
            return <img src={src} alt={alt} loading="lazy" />;
          },
          // Lists
          ul({ children }) { return <ul>{children}</ul>; },
          ol({ children }) { return <ol>{children}</ol>; },
          li({ children }) { return <li>{children}</li>; },
          // Strong / em
          strong({ children }) { return <strong>{children}</strong>; },
          em({ children }) { return <em>{children}</em>; },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Citation-aware content renderer
// ─────────────────────────────────────────────────────────────
function CitedContent({
  content, sources, isStreaming,
}: { content: string; sources?: SourceDocument[]; isStreaming?: boolean }) {
  const [activeSource, setActiveSource] = useState<number | null>(null);

  const sourcesIdx = content.indexOf('\n## Sources');
  const mainContent = sourcesIdx !== -1 ? content.slice(0, sourcesIdx) : content;

  return (
    <div>
      <MarkdownContent content={mainContent} isStreaming={isStreaming} />

      {sources && sources.length > 0 && (
        <div className="mt-4 pt-3 border-t border-border space-y-2">
          <p className="text-[9px] font-bold uppercase tracking-widest text-foreground-3 flex items-center gap-1">
            <BookOpen className="w-3 h-3" /> Sources
          </p>
          <div className="flex flex-wrap gap-1.5">
            {sources.map((src) => (
              <button
                key={src.index}
                onClick={() => setActiveSource(activeSource === src.index ? null : src.index)}
                className={`px-2.5 py-1 rounded-full text-[10px] font-semibold border transition-all ${
                  activeSource === src.index
                    ? 'bg-accent/20 border-accent/40 text-accent'
                    : 'bg-surface-2 border-border text-foreground-3 hover:text-foreground hover:border-accent/30'
                }`}
              >
                [{src.index}] {src.filename}
              </button>
            ))}
          </div>
          {activeSource !== null && (() => {
            const src = sources.find((s) => s.index === activeSource);
            return src ? (
              <div className="p-3 rounded-xl bg-surface-2 border border-border-2 space-y-1.5 animate-slide-up">
                <p className="text-[10px] font-semibold text-foreground">{src.filename}</p>
                {src.distance != null && (
                   <p className="text-[9px] text-foreground-3 font-mono">similarity distance: {Number(src.distance).toFixed(4)}</p>
                )}
                <p className="text-[10px] text-foreground-3 font-mono whitespace-pre-wrap break-all border-l-2 border-border pl-2.5 max-h-32 overflow-y-auto">
                  {src.content?.slice(0, 600)}{src.content?.length > 600 ? '…' : ''}
                </p>
              </div>
            ) : null;
          })()}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Typing indicator
// ─────────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="px-4 py-3 rounded-2xl rounded-bl-sm bg-surface-2 border border-border text-sm inline-flex items-center gap-2">
      <span className="text-xs text-foreground-3 font-medium">Thinking</span>
      <span className="flex gap-1.5 items-center h-4">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '150ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '300ms' }} />
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Action button
// ─────────────────────────────────────────────────────────────
function ActionBtn({
  icon: Icon, label, onClick, active, danger, showLabel,
}: { icon: React.ElementType; label: string; onClick?: () => void; active?: boolean; danger?: boolean; showLabel?: boolean }) {
  return (
    <Tooltip content={!showLabel ? label : undefined} side="top">
      <button
        onClick={onClick} aria-label={label}
        className={`px-2 py-1 rounded-md transition-all text-[11px] flex items-center gap-1.5 ${
          danger  ? 'text-foreground-3 hover:text-red-400 hover:bg-red-400/10' :
          active  ? 'text-accent bg-accent/10' :
                    'text-foreground-3 hover:text-foreground hover:bg-surface-2'}`}
      >
        <Icon className="w-3.5 h-3.5" />
        {showLabel && <span className="text-[10px] font-semibold">{label}</span>}
      </button>
    </Tooltip>
  );
}

// ─────────────────────────────────────────────────────────────
//  Time-aware greeting
// ─────────────────────────────────────────────────────────────
function getTimeGreeting(name: string) {
  const h = new Date().getHours();
  const t = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  if (h >= 5 && h < 12) return {
    headline: name ? `Good morning, ${name}.` : `Good morning.`,
    sub: 'Fresh start, fresh ideas — what are we tackling today?',
  };
  if (h >= 12 && h < 17) return {
    headline: name ? `Good afternoon, ${name}.` : `Good afternoon.`,
    sub: "Peak hours. Let's make every minute count.",
  };
  if (h >= 17 && h < 21) return {
    headline: name ? `Good evening, ${name}.` : `Good evening.`,
    sub: "Day's winding down — what's still on your mind?",
  };
  if (h >= 21) return {
    headline: name ? `Good to see you, ${name}.` : `Good to see you.`,
    sub: "Most people are asleep. We're just warming up.",
  };
  // 0–4 AM deep night
  return {
    headline: name ? `Still up, ${name}?` : `Still at it?`,
    sub: `It's ${t} and you're still going — respect.`,
  };
}

// ─────────────────────────────────────────────────────────────
//  Error card — replaces raw italic error text
// ─────────────────────────────────────────────────────────────
function parseErrorFromContent(content: string): { clean: string; error: string | null } {
  // Match error lines appended by the streaming handler
  const lines = content.split('\n');
  const errLines: string[] = [];
  const cleanLines: string[] = [];
  for (const line of lines) {
    const m = line.trim().match(/^\*\[(.+?)\]\*$/);
    if (m) errLines.push(m[1]);
    else cleanLines.push(line);
  }
  const clean = cleanLines.join('\n').trim();
  const error = errLines.length ? errLines.join(' ') : null;
  return { clean, error };
}

function resolveProvider(modelId: string): string {
  const m = modelId.toLowerCase();
  if (m.startsWith('openrouter/')) return 'openrouter';
  if (m.includes('gemini') || m.includes('google')) return 'google';
  if (m.includes('gpt') || m.includes('o1-')) return 'openai';
  if (m.includes('claude')) return 'anthropic';
  if (m.includes('deepseek')) return 'deepseek';
  if (m.includes('llama') || m.includes('mixtral')) return 'groq';
  if (m.includes('glm')) return 'glm';
  if (m.includes('qwen')) return 'alibaba';
  return 'google';
}

function formatShortTitle(text: string): string {
  if (!text || !text.trim()) return 'New Chat';
  let clean = text.trim();
  if (clean.includes('[Attached File:')) {
    clean = clean.split('[Attached File:')[0].trim();
  }
  const firstLine = clean.split('\n')[0] || clean;
  const stripped = firstLine
    .replace(/^(can you|please|help me|how to|write|create|explain|tell me|what is|who is|show me)\s+/i, '')
    .replace(/[?.,!\"':;]+$/, '')
    .trim();
  const words = (stripped || firstLine).split(/\s+/).slice(0, 5);
  const result = words.join(' ');
  return result.length > 35 ? result.slice(0, 35) + '…' : result || 'New Chat';
}

function ErrorCard({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const [showDetails, setShowDetails] = useState(false);
  const [copied, setCopied] = useState(false);
  const navigate = useNavigate();

  const handleCopy = () => {
    navigator.clipboard.writeText(message);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const needsKeyConfig = message.toLowerCase().includes('key') || message.toLowerCase().includes('auth') || message.toLowerCase().includes('provider') || message.toLowerCase().includes('unauthorized');

  // Short, clean, elegant summary text (ChatGPT style)
  const cleanSummary = (() => {
    const m = message.toLowerCase();
    if (m.includes('missing api key') || m.includes('missing or unconfigured api key'))
      return 'API key required for the selected model';
    if (m.includes('invalid api key') || m.includes('invalid key') || m.includes('verification failed'))
      return 'Invalid API key. Please check your key in Settings';
    if (m.includes('quota') || m.includes('402') || m.includes('credits'))
      return 'Provider billing quota or credits exceeded';
    if (m.includes('429') || m.includes('rate limit'))
      return 'Rate limit reached. Please wait a moment';
    if (m.includes('backend unavailable') || m.includes('failed to connect') || m.includes('connection lost'))
      return 'Unable to connect to the server';
    return 'There was an error generating a response';
  })();

  return (
    <div className="my-3 flex flex-col items-start gap-2.5 text-left">
      <p className="text-sm font-medium text-foreground/90 tracking-tight leading-relaxed">
        {cleanSummary}
      </p>

      <div className="flex items-center gap-2 flex-wrap">
        {onRetry && (
          <button
            onClick={onRetry}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-900/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Regenerate
          </button>
        )}

        {needsKeyConfig && (
          <button
            onClick={() => navigate('/settings?tab=models')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold shadow-md shadow-violet-900/20 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <KeyRound className="w-3.5 h-3.5" />
            Configure Key
          </button>
        )}

        <button
          onClick={() => setShowDetails(!showDetails)}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          {showDetails ? 'Hide details' : 'Details'}
        </button>
      </div>

      {showDetails && (
        <div className="mt-1 w-full max-w-xl rounded-xl border border-border bg-black/40 p-3 font-mono text-[11px] text-muted-foreground leading-relaxed overflow-x-auto relative group">
          <div className="flex items-center justify-between gap-2 mb-1.5 pb-1 border-b border-white/10">
            <span className="text-[10px] uppercase font-semibold text-rose-400">Technical Details</span>
            <button
              onClick={handleCopy}
              className="text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              {copied ? 'Copied' : 'Copy Trace'}
            </button>
          </div>
          <p className="whitespace-pre-wrap break-words">{message}</p>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Main ChatPage
// ─────────────────────────────────────────────────────────────
export default function ChatPage() {
  const { chatId: urlChatId } = useParams<{ chatId?: string }>();

  const chats = useChatStore((s) => s.chats);
  const activeChatId = useChatStore((s) => s.activeChatId);
  const messages = useChatStore((s) => s.messages);
  const activeModel = useChatStore((s) => s.activeModel);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const providers = useChatStore((s) => s.providers);
  const loadingKeys = useChatStore((s) => s.keysLoading);

  const setChats = useChatStore((s) => s.setChats);
  const setActiveChatId = useChatStore((s) => s.setActiveChatId);
  const setMessages = useChatStore((s) => s.setMessages);
  const setMessagesForChat = useChatStore((s) => s.setMessagesForChat);
  const hasCachedMessages = useChatStore((s) => s.hasCachedMessages);
  const setActiveModel = useChatStore((s) => s.setActiveModel);
  const setIsStreaming = useChatStore((s) => s.setIsStreaming);
  const addChat = useChatStore((s) => s.addChat);
  const removeChat = useChatStore((s) => s.removeChat);
  const updateChat = useChatStore((s) => s.updateChat);
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const setProviders = useChatStore((s) => s.setProviders);
  const setKeysLoading = useChatStore((s) => s.setKeysLoading);

  const { developerMode, toggleDeveloperMode, language } = useUIStore();
  const { token, user, logout } = useAuthStore();
  const firstName = user?.full_name?.trim().split(/\s+/)[0] || user?.email?.split('@')[0] || '';
  const greeting   = getTimeGreeting(firstName);
  const userInitial = user?.full_name
    ? user.full_name.charAt(0).toUpperCase()
    : user?.email.charAt(0).toUpperCase() ?? 'U';

  const validateChatRequest = useCallback((modelId: string, providerId: string): string | null => {
    ProviderKeyManager.refresh();
    if (!token) {
      return 'Authentication failed - Invalid or missing user token. Please log in again.';
    }
    const supportedProviders = ['google', 'openai', 'anthropic', 'deepseek', 'groq', 'openrouter', 'glm', 'alibaba'];
    if (!supportedProviders.includes(providerId)) {
      return `Invalid model provider - The resolved provider "${providerId}" is not supported.`;
    }
    const matchingProv = providers.find((p) => p.id === providerId);
    if (!matchingProv || matchingProv.status !== 'VERIFIED') {
      if (!ProviderKeyManager.hasKey(providerId)) {
        return `Authentication failed - Missing or unconfigured API key for provider ${providerId.toUpperCase()}. Update it in Settings.`;
      }
    }
    const hasLocal = ProviderKeyManager.hasKey(providerId);
    const backendSaved = matchingProv?.saved;
    if (!hasLocal && !backendSaved) {
      return `Authentication failed - Missing or empty API key for provider ${providerId.toUpperCase()}. Update it in Settings.`;
    }
    const normalizedModel = modelId.toLowerCase();
    const isGeminiModel = normalizedModel.includes('gemini');
    const isOpenAIModel = normalizedModel.includes('gpt') || normalizedModel.includes('o1-');
    const isClaudeModel = normalizedModel.includes('claude');
    const isDeepseekModel = normalizedModel.includes('deepseek');
    const isGroqModel = normalizedModel.includes('llama') || normalizedModel.includes('mixtral');
    if (providerId === 'google' && !isGeminiModel) {
      return `Provider mismatch - Model "${modelId}" does not belong to provider GOOGLE/GEMINI.`;
    }
    if (providerId === 'openai' && !isOpenAIModel) {
      return `Provider mismatch - Model "${modelId}" does not belong to provider OPENAI.`;
    }
    if (providerId === 'anthropic' && !isClaudeModel) {
      return `Provider mismatch - Model "${modelId}" does not belong to provider ANTHROPIC.`;
    }
    if (providerId === 'deepseek' && !isDeepseekModel) {
      return `Provider mismatch - Model "${modelId}" does not belong to provider DEEPSEEK.`;
    }
    if (providerId === 'groq' && !isGroqModel) {
      return `Provider mismatch - Model "${modelId}" does not belong to provider GROQ.`;
    }
    return null;
  }, [token, providers]);

  // ── Toast notification system ─────────────────────────────────
  const { toasts, addToast, removeToast } = useToast();

  // ── Core UI state ────────────────────────────────────────────
  const [convoOpen, setConvoOpen]                 = useState(true);
  const [showUserMenu, setShowUserMenu]           = useState(false);
  const [searchQuery, setSearchQuery]             = useState('');
  const [copiedMsgId, setCopiedMsgId]             = useState<string | null>(null);
  const [showScrollBtn, setShowScrollBtn]         = useState(false);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [activeHudTab, setActiveHudTab]           = useState<'flow' | 'context' | 'logs'>('flow');
  const [activeRowMenuId, setActiveRowMenuId]     = useState<string | null>(null);
  const [renamingId, setRenamingId]               = useState<string | null>(null);
  const [renameValue, setRenameValue]             = useState('');
  const [editingMsgId, setEditingMsgId]           = useState<string | null>(null);
  const [selectedUserFile, setSelectedUserFile]   = useState<{ name: string; content: string } | null>(null);
  const [editValue, setEditValue]                 = useState('');
  const [connectedChat, setConnectedChat]         = useState<{ id: string; title: string } | null>(null);
  const editTextareaRef                           = useRef<HTMLTextAreaElement>(null);
  // Guard: prevent concurrent new-chat creation
  const creatingChatRef                        = useRef(false);
  const skipFetchRef                           = useRef(false);
  // ── Messages loading — prevents empty-state flash when switching chats
  const [messagesLoading, setMessagesLoading]  = useState(false);
  // ── Questions Nav panel ──────────────────────────────────────
  const [questionsPopupOpen, setQuestionsPopupOpen] = useState(false);
  const popupLeaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [highlightedMsgId, setHighlightedMsgId] = useState<string | null>(null);
  // ── Chat minimap scroll state ─────────────────────────────────
  const [minimapThumbTop, setMinimapThumbTop]   = useState(0);
  const [minimapThumbHeight, setMinimapThumbHeight] = useState(20);
  const minimapTrackRef                         = useRef<HTMLDivElement>(null);
  // ── Per-chat document list ────────────────────────────────────
  const [chatDocuments, setChatDocuments]       = useState<any[]>([]);

  // ── Modals & Overlays ────────────────────────────────────────
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false);

  // ── Pinned & Favorite Chats (Local Persistence) ──────────────
  const [pinnedChats, setPinnedChats] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('omni_pinned_chats') || '[]'); } catch { return []; }
  });
  const [favoriteChats, setFavoriteChats] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('omni_favorite_chats') || '[]'); } catch { return []; }
  });

  // ── DevHUD Resizing ──────────────────────────────────────────
  const [hudWidth, setHudWidth] = useState(380);
  const [hudMinimized, setHudMinimized] = useState(false);
  const isResizingRef = useRef(false);

  // ── Share & Export state ─────────────────────────────────────
  const [copiedShareLink, setCopiedShareLink] = useState(false);

  // ── More Dropdowns & Archiving ───────────────────────────────
  const [menuOpen, setMenuOpen]               = useState(false);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [archivedChats, setArchivedChats]     = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('omni_archived_chats') || '[]'); } catch { return []; }
  });
  const [filesModalOpen, setFilesModalOpen]   = useState(false);
  // Message element refs for jump-to-question
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // ── Refs ─────────────────────────────────────────────────────
  const messagesEndRef    = useRef<HTMLDivElement>(null);
  const chatScrollRef     = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const navigate = useNavigate();



  const PROVIDER_DISPLAY_NAMES: Record<string, string> = {
    google: 'Google Gemini',
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    deepseek: 'DeepSeek',
    groq: 'Groq',
    openrouter: 'OpenRouter',
    glm: 'GLM',
    alibaba: 'Alibaba',
  };

  const rawModels = providers
    .filter((p) => p.status === 'VERIFIED')
    .flatMap((p) => p.availableModels.map((m) => {
      const isPremium = m.toLowerCase().includes("pro") || m.toLowerCase().includes("ultra") || m.toLowerCase().includes("max") || m.toLowerCase().includes("o1");
      return {
        id: m,
        name: m,
        provider: PROVIDER_DISPLAY_NAMES[p.id] || p.id,
        apiProvider: p.id,
        icon: isPremium ? Sparkles : Cpu,
        desc: `Model ${m} provided by ${PROVIDER_DISPLAY_NAMES[p.id] || p.id}`
      };
    }));

  const modelsMap = new Map();
  rawModels.forEach(m => {
    if (!modelsMap.has(m.id)) {
      modelsMap.set(m.id, m);
    }
  });
  const models = Array.from(modelsMap.values());

  const currentModel = models.find((m) => m.id === activeModel) || models[0] || { id: '', name: 'No Models', provider: 'None', icon: Cpu, desc: 'Please add keys in Settings' };
  const activeChat   = chats.find((c) => c.id === activeChatId);
  const isLocked     = !loadingKeys && models.length === 0;

  // ── Keyboard Shortcuts Integration ──────────────────────────
  useKeyboardShortcuts({
    onNewChat: () => handleCreateChat(),
    onOpenSearch: () => setGlobalSearchOpen(true),
    onShowShortcuts: () => setShortcutsOpen(true),
    onEscape: () => {
      setShortcutsOpen(false);
      setGlobalSearchOpen(false);
    }
  });

  // Listen to custom sidebar search event — focus inline sidebar search input
  useEffect(() => {
    const handleOpenSearchEvent = () => {
      setConvoOpen(true);
      setTimeout(() => {
        const inputEl = document.querySelector('input[placeholder="Search conversations..."]') as HTMLInputElement;
        inputEl?.focus();
      }, 50);
    };
    window.addEventListener('omni:open-search', handleOpenSearchEvent);
    return () => window.removeEventListener('omni:open-search', handleOpenSearchEvent);
  }, []);

  // ── Fetch verified API Keys / Providers — runs once on mount ─────────────
  // Populates the shared store so SettingsPage stays in sync.
  useEffect(() => {
    if (!loadingKeys && providers.length > 0) return;
    async function loadProviders() {
      setKeysLoading(true);
      try {
        const data = await apiRequest('/providers');
        setProviders(data);
      } catch { /* silent */ }
      finally { setKeysLoading(false); }
    }
    loadProviders();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Auto-select first available model when no valid model is active ──
  useEffect(() => {
    if (!loadingKeys && models.length > 0 && !models.some((m) => m.id === activeModel)) {
      setActiveModel(models[0].id);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingKeys, models]);

  // ── Fetch chats / messages & documents ───────────────────────
  const fetchDocuments = async () => {
    try {
      await apiRequest('/documents');
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  };

  const fetchChatDocuments = useCallback(async (chatId: string) => {
    try {
      const data = await apiRequest(`/documents?chat_id=${chatId}`);
      setChatDocuments(data);
    } catch {
      setChatDocuments([]);
    }
  }, []);

  // Refresh per-chat docs when active chat changes
  useEffect(() => {
    if (activeChatId) fetchChatDocuments(activeChatId);
    else setChatDocuments([]);
  }, [activeChatId, fetchChatDocuments]);

  // Initial mount load for chats & documents — runs ONCE per auth token
  useEffect(() => {
    let active = true;
    apiRequest('/chats')
      .then((loadedChats) => {
        if (!active) return;
        setChats(loadedChats);

        // Active conversation restoration logic on initial page load:
        if (urlChatId && loadedChats.some((c: any) => c.id === urlChatId)) {
          setActiveChatId(urlChatId);
        } else if (urlChatId && !loadedChats.some((c: any) => c.id === urlChatId)) {
          setActiveChatId(null);
          navigate('/', { replace: true });
        }
      })
      .catch(() => {});
    fetchDocuments();
    return () => { active = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Route URL synchronization for browser Back/Forward navigation
  useEffect(() => {
    if (urlChatId && urlChatId !== activeChatId) {
      setActiveChatId(urlChatId);
    }
  }, [urlChatId, activeChatId, setActiveChatId]);

  // Fetch messages for active chat — uses messageCache for 0ms instant display.
  // NOTE: isStreaming is intentionally NOT in deps — we must not re-fetch when
  // streaming ends, as that would race-overwrite locally accumulated messages.
  useEffect(() => {
    if (activeChatId) {
      if (skipFetchRef.current) {
        skipFetchRef.current = false;
        return;
      }

      // Safety: never fetch while a stream is in progress
      if (useChatStore.getState().isStreaming) {
        return;
      }

      // Do not attempt network GET for temp optimistic chat IDs
      if (activeChatId.startsWith('temp-')) {
        setMessages([]);
        setMessagesLoading(false);
        return;
      }

      let active = true;
      const isCached = hasCachedMessages(activeChatId);
      if (!isCached) {
        setMessagesLoading(true);
      }
      apiRequest(`/chats/${activeChatId}`)
        .then((msgs) => {
          if (!active) return;
          // If streaming started while we were fetching, discard the result
          if (useChatStore.getState().isStreaming) return;

          const hydratedMsgs = msgs.map((m: import('../types/chat').Message) => ({
            ...m,
            imagePreviewUrls:
              m.images && m.images.length > 0
                ? m.images.map((img) => `data:${img.mimeType};base64,${img.base64}`)
                : m.imagePreviewUrls,
          }));

          const liveMsgs = useChatStore.getState().messages;
          const cachedMsgs = useChatStore.getState().messageCache[activeChatId];
          const hasLocalContent = (liveMsgs && liveMsgs.length > 0) || (cachedMsgs && cachedMsgs.length > 0);

          // DO NOT overwrite active in-memory messages if backend returns fewer messages than local
          if (hasLocalContent && hydratedMsgs.length < (liveMsgs?.length || 0)) {
            setMessagesLoading(false);
            return;
          }

          setMessagesForChat(activeChatId, hydratedMsgs);
          setMessagesLoading(false);
        })
        .catch(() => { if (active) setMessagesLoading(false); });
      return () => { active = false; };
    } else {
      setMessages([]);
      setMessagesLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChatId, setMessagesForChat, setMessages, hasCachedMessages]);

  useEffect(() => {
    setCopiedShareLink(false);
  }, [activeChatId]);

  // ── Auto-scroll ──────────────────────────────────────────────
  useEffect(() => {
    if (isStreaming) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isStreaming]);

  // ── HUD: track last assistant message ───────────────────────
  const assistantMessages = messages.filter((m) => m.role === 'assistant');
  const lastAssistantMsg  = assistantMessages[assistantMessages.length - 1];
  useEffect(() => {
    if (lastAssistantMsg && (isStreaming || !selectedMessageId)) setSelectedMessageId(lastAssistantMsg.id);
    if (!lastAssistantMsg) setSelectedMessageId(null);
  }, [messages, isStreaming, lastAssistantMsg, selectedMessageId]);

  // ── Scroll detection + minimap sync ──────────────────────────
  const handleScroll = () => {
    const el = chatScrollRef.current;
    if (!el) return;
    setShowScrollBtn(el.scrollHeight - el.scrollTop - el.clientHeight > 120);
    // Update minimap thumb
    const scrollable = el.scrollHeight - el.clientHeight;
    const scrollFrac = scrollable > 0 ? el.scrollTop / scrollable : 0;
    const thumbH = Math.max(16, (el.clientHeight / el.scrollHeight) * 100);
    setMinimapThumbHeight(thumbH);
    setMinimapThumbTop(scrollFrac * (100 - thumbH));
  };
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  // ── Jump to question ─────────────────────────────────────────
  const jumpToMessage = useCallback((msgId: string) => {
    const el = messageRefs.current[msgId];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setHighlightedMsgId(msgId);
      setTimeout(() => setHighlightedMsgId(null), 1200);
    }
  }, []);

  // ── Minimap click-to-scroll ───────────────────────────────────
  const handleMinimapClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const el = chatScrollRef.current;
    const track = minimapTrackRef.current;
    if (!el || !track) return;
    const rect = track.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    el.scrollTop = frac * (el.scrollHeight - el.clientHeight);
  }, []);

  // ── User questions list (for Q&A nav) ────────────────────────
  const userQuestions = useMemo(() => {
    return messages
      .filter((m) => m.role === 'user')
      .map((m, i) => ({ id: m.id, index: i + 1, content: m.content }));
  }, [messages]);

  // ── Chat CRUD ────────────────────────────────────────────────
  const handleCreateChat = useCallback(() => {
    setActiveChatId(null);
    setMessages([]);
    navigate('/');
  }, [setActiveChatId, setMessages, navigate]);

  const handleDeleteChat = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    // Immediate 0ms optimistic removal
    removeChat(id);
    setPinnedChats(pinnedChats.filter((cid) => cid !== id));
    setFavoriteChats(favoriteChats.filter((cid) => cid !== id));
    setArchivedChats(archivedChats.filter((cid) => cid !== id));
    if (activeChatId === id || urlChatId === id) {
      setActiveChatId(null);
      setMessages([]);
      navigate('/', { replace: true });
    }
    // Background network request
    apiRequest(`/chats/${id}`, { method: 'DELETE' }).catch((err) => {
      console.error('Failed to delete chat:', err);
    });
  };

  const handleRenameChat = (id: string) => {
    const newTitle = renameValue.trim();
    if (!newTitle) { setRenamingId(null); return; }
    // Immediate 0ms optimistic rename
    setChats(chats.map((c) => c.id === id ? { ...c, title: newTitle } : c));
    setRenamingId(null);
    // Background network request
    apiRequest(`/chats/${id}`, { method: 'PATCH', json: { title: newTitle } }).catch((err) => {
      console.error('Failed to rename chat:', err);
    });
  };

  // ── Pin Toggle ──────────────────────────────────────────────
  const togglePinChat = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    let next: string[];
    if (pinnedChats.includes(id)) {
      next = pinnedChats.filter((cid) => cid !== id);
    } else {
      next = [...pinnedChats, id];
    }
    setPinnedChats(next);
    localStorage.setItem('omni_pinned_chats', JSON.stringify(next));
  };

  // ── Archive Toggle ──────────────────────────────────────────
  const toggleArchiveChat = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    let next: string[];
    if (archivedChats.includes(id)) {
      next = archivedChats.filter((cid) => cid !== id);
    } else {
      next = [...archivedChats, id];
    }
    setArchivedChats(next);
    localStorage.setItem('omni_archived_chats', JSON.stringify(next));
  };

  // ── Stop generation ──────────────────────────────────────────
  const handleStopGeneration = () => { abortControllerRef.current?.abort(); setIsStreaming(false); };

  // ── Send message ─────────────────────────────────────────────
  const handleSendMessage = useCallback(async (text: string, imagesToSend: { base64: string; mimeType: string }[] = []) => {
    const trimmed = text.trim();
    if ((!trimmed && imagesToSend.length === 0) || isStreaming) return;

    let chatId = activeChatId;
    let isNewChat = false;

    if (!chatId) {
      if (creatingChatRef.current) return;
      creatingChatRef.current = true;
      isNewChat = true;
    }

    const userMsgId = crypto.randomUUID();
    const asstMsgId = crypto.randomUUID();

    const userMsg = {
      id: userMsgId,
      chat_id: chatId || 'temp-chat-id',
      parent_id: messages.length > 0 ? messages[messages.length - 1].id : null,
      role: 'user' as const,
      content: trimmed,
      tool_calls: null,
      developer_metrics: null,
      created_at: new Date().toISOString(),
      imagePreviewUrls: imagesToSend.length > 0
        ? imagesToSend.map((img) => `data:${img.mimeType};base64,${img.base64}`)
        : undefined,
    };

    addMessage(userMsg);
    addMessage({
      id: asstMsgId,
      chat_id: chatId || 'temp-chat-id',
      parent_id: userMsg.id,
      role: 'assistant' as const,
      content: '',
      tool_calls: null,
      developer_metrics: null,
      created_at: new Date().toISOString(),
    });

    setIsStreaming(true);

    if (isNewChat) {
      try {
        const initialTitle = formatShortTitle(trimmed);
        const nc = await apiRequest('/chats', { method: 'POST', json: { title: initialTitle } });
        addChat(nc);
        chatId = nc.id;
        skipFetchRef.current = true;
        setActiveChatId(chatId);
        navigate(`/c/${chatId}`, { replace: true });
      } catch (err) {
        creatingChatRef.current = false;
        setIsStreaming(false);
        updateMessage(asstMsgId, { content: '*[Failed to create conversation session]*' });
        return;
      } finally {
        creatingChatRef.current = false;
      }
    }

    // ── Background-upload any attached images to Documents API ─────────────
    // This makes images show up in the Files section of the chat.
    if (imagesToSend.length > 0 && chatId) {
      (async () => {
        try {
          for (const img of imagesToSend) {
            const mimeToExt: Record<string, string> = {
              'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif',
              'image/bmp': '.bmp', 'image/tiff': '.tiff', 'image/webp': '.png',
            };
            const ext = mimeToExt[img.mimeType] || '.png';
            const byteChars = atob(img.base64);
            const byteArr = new Uint8Array(byteChars.length);
            for (let i = 0; i < byteChars.length; i++) byteArr[i] = byteChars.charCodeAt(i);
            const blob = new Blob([byteArr], { type: img.mimeType });
            const filename = `image_${Date.now()}${ext}`;
            const file = new File([blob], filename, { type: img.mimeType });
            const fd = new FormData();
            fd.append('file', file);
            fd.append('chat_id', chatId!);
            await fetch('/api/v1/documents/upload', {
              method: 'POST',
              headers: { Authorization: `Bearer ${token}` },
              body: fd,
            });
          }
          // Refresh the files list so the Files badge and modal update
          if (chatId) fetchChatDocuments(chatId);
        } catch {
          // silently ignore — not critical path
        }
      })();
    }

    const resolvedProv = currentModel?.apiProvider || resolveProvider(activeModel);
    const validationError = validateChatRequest(activeModel, resolvedProv);
    if (validationError) {
      updateMessage(asstMsgId, { content: `*[${validationError}]*` });
      setIsStreaming(false);
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let asstText = '';

    try {
      let payloadContent = language && language !== 'Auto-detect' ? `${trimmed}\n\n(Note: Please reply in ${language})` : trimmed;
      if (connectedChat) {
        let refMsgs = useChatStore.getState().messageCache[connectedChat.id];
        if (!refMsgs) {
          try {
            refMsgs = await apiRequest(`/chats/${connectedChat.id}`);
          } catch { /* fallback */ }
        }
        if (refMsgs && refMsgs.length > 0) {
          const summaryLines = refMsgs
            .filter((m: any) => m.role === 'user' || m.role === 'assistant')
            .slice(-6)
            .map((m: any) => `[${m.role.toUpperCase()}]: ${m.content.slice(0, 300)}`)
            .join('\n');
          payloadContent = `[Connected Reference Context from Chat: "${connectedChat.title}"]\n${summaryLines}\n[End of Referenced Context]\n\n${payloadContent}`;
        }
      }
      const allKeys = ProviderKeyManager.refresh();
      const headersInit: Record<string, string> = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        'x-api-keys': JSON.stringify(allKeys),
      };

      let res = await fetch(`/api/v1/chats/${chatId}/messages`, {
        method: 'POST',
        headers: headersInit,
        body: JSON.stringify({ content: payloadContent, model: activeModel, parent_message_id: userMsg.parent_id, images: imagesToSend }),
        signal: controller.signal,
      });

      if (res.status === 401 && token) {
        try {
          const refreshRes = await fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'include' });
          if (refreshRes.ok) {
            const refreshData = await refreshRes.json();
            const newToken = refreshData.access_token;
            if (user) useAuthStore.getState().login(newToken, user);
            headersInit['Authorization'] = `Bearer ${newToken}`;
            res = await fetch(`/api/v1/chats/${chatId}/messages`, {
              method: 'POST',
              headers: headersInit,
              body: JSON.stringify({ content: payloadContent, model: activeModel, parent_message_id: userMsg.parent_id, images: imagesToSend }),
              signal: controller.signal,
            });
          }
        } catch { /* proceed to check res.ok */ }
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      
      console.log(res.headers.get("content-type"));
      const reader  = res.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      if (!reader) throw new Error('No reader');

      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        console.log("DONE:", done);
        console.log("CHUNK:", decoder.decode(value || new Uint8Array()));
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine || !trimmedLine.startsWith('data: ')) continue;
          const raw = trimmedLine.substring(6);
          if (raw === '[DONE]') continue;
          try {
            const parsed = JSON.parse(raw);
            if (parsed.event === 'chunk') {
              asstText += parsed.text;
              updateMessage(asstMsgId, { content: asstText });
            } else if (parsed.event === 'metrics') {
              updateMessage(asstMsgId, { developer_metrics: parsed.metrics });
            } else if (parsed.event === 'title') {
              const { chats: liveChats, updateChat: liveUpdateChat } = useChatStore.getState();
              const liveChat = liveChats.find((c: any) => c.id === chatId);
              if (liveChat) liveUpdateChat({ ...liveChat, title: parsed.title });
            } else if (parsed.event === 'error') {
              asstText += `\n\n*[Error: ${parsed.detail || 'Failed to generate response'}]*`;
              updateMessage(asstMsgId, { content: asstText });
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        const errorMsg = err.message || '';
        const formattedErr = errorMsg.includes('401')
          ? 'Authentication failed - Invalid or missing API key (HTTP 401)'
          : `Error: ${errorMsg || 'Response interrupted or connection lost'}`;
        updateMessage(asstMsgId, { content: asstText + `\n\n*[${formattedErr}]*` });
      }
    } finally {
      setIsStreaming(false);
      const { chats: liveChats, updateChat: liveUpdateChat } = useChatStore.getState();
      const liveChat = liveChats.find((c: any) => c.id === chatId);
      if (liveChat && liveChat.title === 'New Chat' && trimmed) {
        const autoTitle = formatChatTitle(trimmed);
        liveUpdateChat({ ...liveChat, title: autoTitle });
        apiRequest(`/chats/${chatId}`, { method: 'PATCH', json: { title: autoTitle } }).catch(() => {});
      }
    }
  }, [activeChatId, isStreaming, messages, activeModel, language, token, addChat, addMessage, updateMessage, setActiveChatId, setIsStreaming, navigate, currentModel, validateChatRequest]);

  // ── Message actions ──────────────────────────────────────────
  const handleCopyMessage = (id: string, content: string) => {
    navigator.clipboard.writeText(content).then(() => {
      setCopiedMsgId(id);
      setTimeout(() => setCopiedMsgId(null), 2000);
      addToast('Copied to clipboard', 'success', 2000);
    });
  };

  const handleStartEdit = (id: string, content: string) => {
    setEditingMsgId(id); setEditValue(content);
    setTimeout(() => { editTextareaRef.current?.focus(); editTextareaRef.current?.select(); }, 50);
  };

  const handleSubmitEdit = async (msgId: string) => {
    const newText = editValue.trim();
    if (!newText || !activeChatId || isStreaming) { setEditingMsgId(null); return; }
    const editIdx = messages.findIndex((m) => m.id === msgId);
    if (editIdx === -1) { setEditingMsgId(null); return; }

    setEditingMsgId(null);

    const trimmedMessages = messages.slice(0, editIdx);

    // Build the new user message and empty assistant placeholder
    const newUserMsg = {
      id: crypto.randomUUID(),
      chat_id: activeChatId,
      parent_id: trimmedMessages.length > 0 ? trimmedMessages[trimmedMessages.length - 1].id : null,
      role: 'user' as const,
      content: newText,
      tool_calls: null,
      developer_metrics: null,
      created_at: new Date().toISOString(),
    };
    const asstId = crypto.randomUUID();
    const newAsstMsg = {
      id: asstId,
      chat_id: activeChatId,
      parent_id: newUserMsg.id,
      role: 'assistant' as const,
      content: '',
      tool_calls: null,
      developer_metrics: null,
      created_at: new Date().toISOString(),
    };

    // Atomic update: replace everything from editIdx onward in one setMessages call
    // This avoids the race condition between setMessages and addMessage
    setMessages([...trimmedMessages, newUserMsg, newAsstMsg]);
    setIsStreaming(true);

    const resolvedProv = currentModel?.apiProvider || resolveProvider(activeModel);
    const validationError = validateChatRequest(activeModel, resolvedProv);
    if (validationError) {
      updateMessage(asstId, { content: `*[${validationError}]*` });
      setIsStreaming(false);
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let asstText = '';

    try {
      const payloadContent = language && language !== 'Auto-detect' ? `${newText}\n\n(Note: Please reply in ${language})` : newText;
      const allKeys = ProviderKeyManager.getAllKeys();
      const headersInit: Record<string, string> = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        'x-api-keys': JSON.stringify(allKeys),
      };

      let res = await fetch(`/api/v1/chats/${activeChatId}/messages`, {
        method: 'POST',
        headers: headersInit,
        body: JSON.stringify({ content: payloadContent, model: activeModel, parent_message_id: newUserMsg.parent_id, images: [] }),
        signal: controller.signal,
      });

      if (res.status === 401 && token) {
        try {
          const refreshRes = await fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'include' });
          if (refreshRes.ok) {
            const refreshData = await refreshRes.json();
            const newToken = refreshData.access_token;
            if (user) useAuthStore.getState().login(newToken, user);
            headersInit['Authorization'] = `Bearer ${newToken}`;
            res = await fetch(`/api/v1/chats/${activeChatId}/messages`, {
              method: 'POST',
              headers: headersInit,
              body: JSON.stringify({ content: payloadContent, model: activeModel, parent_message_id: newUserMsg.parent_id, images: [] }),
              signal: controller.signal,
            });
          }
        } catch { /* proceed to check res.ok */ }
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      if (!reader) throw new Error('No reader');

      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;
          const raw = trimmed.substring(6);
          if (raw === '[DONE]') continue;
          try {
            const parsed = JSON.parse(raw);
            if (parsed.event === 'chunk') {
              asstText += parsed.text;
              updateMessage(asstId, { content: asstText });
            } else if (parsed.event === 'metrics') {
              updateMessage(asstId, { developer_metrics: parsed.metrics });
            } else if (parsed.event === 'error') {
              asstText += `\n\n*[Error: ${parsed.detail || 'Failed to generate response'}]*`;
              updateMessage(asstId, { content: asstText });
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        const errorMsg = err.message || '';
        const formattedErr = errorMsg.includes('401')
          ? 'Authentication failed - Invalid or missing API key (HTTP 401)'
          : `Error: ${errorMsg || 'Response interrupted or connection lost'}`;
        updateMessage(asstId, { content: asstText + `\n\n*[${formattedErr}]*` });
      }
    } finally {
      setIsStreaming(false);
    }
  };

  const handleCancelEdit = () => { setEditingMsgId(null); setEditValue(''); };

  const handleRetry = async (assistantMsgIdx: number) => {
    if (isStreaming || !activeChatId) return;

    // Find the preceding user message
    let userMsgIdx = -1;
    for (let i = assistantMsgIdx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { userMsgIdx = i; break; }
    }
    if (userMsgIdx === -1) return;

    const retryText      = messages[userMsgIdx].content;
    const trimmedMsgs    = messages.slice(0, userMsgIdx);

    // Build replacement user + placeholder assistant messages
    const newUserMsg = {
      id: crypto.randomUUID(), chat_id: activeChatId,
      parent_id: trimmedMsgs.length > 0 ? trimmedMsgs[trimmedMsgs.length - 1].id : null,
      role: 'user' as const, content: retryText,
      tool_calls: null, developer_metrics: null, created_at: new Date().toISOString(),
    };
    const retryAsstId = crypto.randomUUID();
    const newAsstMsg = {
      id: retryAsstId, chat_id: activeChatId, parent_id: newUserMsg.id,
      role: 'assistant' as const, content: '',
      tool_calls: null, developer_metrics: null, created_at: new Date().toISOString(),
    };

    // Atomic: replace from userMsgIdx onward — no race condition
    setMessages([...trimmedMsgs, newUserMsg, newAsstMsg]);
    setIsStreaming(true);

    const resolvedProv = currentModel?.apiProvider || resolveProvider(activeModel);
    const validationError = validateChatRequest(activeModel, resolvedProv);
    if (validationError) {
      updateMessage(retryAsstId, { content: `*[${validationError}]*` });
      setIsStreaming(false);
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let retryAsstText = '';

    try {
      const payloadContent = language && language !== 'Auto-detect' ? `${retryText}\n\n(Note: Please reply in ${language})` : retryText;
      const allKeys = ProviderKeyManager.getAllKeys();
      const headersInit: Record<string, string> = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      };
      if (Object.keys(allKeys).length > 0) {
        headersInit['x-api-keys'] = JSON.stringify(allKeys);
      }

      const res = await fetch(`/api/v1/chats/${activeChatId}/messages`, {
        method: 'POST',
        headers: headersInit,
        body: JSON.stringify({
          content: payloadContent, model: activeModel,
          parent_message_id: newUserMsg.parent_id, images: [],
        }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      if (!reader) throw new Error('No reader');

      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
          const t = line.trim();
          if (!t || !t.startsWith('data: ')) continue;
          const raw = t.substring(6);
          if (raw === '[DONE]') continue;
          try {
            const p = JSON.parse(raw);
            if (p.event === 'chunk') {
              retryAsstText += p.text;
              updateMessage(retryAsstId, { content: retryAsstText });
            } else if (p.event === 'metrics') {
              updateMessage(retryAsstId, { developer_metrics: p.metrics });
            } else if (p.event === 'error') {
              retryAsstText += `\n\n*[Error: ${p.detail || 'Failed to generate response'}]*`;
              updateMessage(retryAsstId, { content: retryAsstText });
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        const errorMsg = err.message || '';
        const formattedErr = errorMsg.includes('401')
          ? 'Authentication failed - Invalid or missing API key (HTTP 401)'
          : `Error: ${errorMsg || 'Response interrupted'}`;
        updateMessage(retryAsstId, { content: retryAsstText + `\n\n*[${formattedErr}]*` });
      }
    } finally {
      setIsStreaming(false);
    }
  };

  const handleDeleteMessage = (msgId: string) => {
    const nextMsgs = messages.filter((m) => m.id !== msgId);
    setMessages(nextMsgs);
  };

  // ── Share ────────────────────────────────────────────────────
  const handleToggleShare = async (chatId: string, isShared: boolean, isLive = false) => {
    try {
      const updated = await apiRequest(`/chats/${chatId}/share`, { method: 'POST', json: { is_shared: isShared, is_live: isLive } });
      updateChat(updated);
    } catch { /* silent */ }
  };

  // ── DevHUD Panel Resize ──────────────────────────────────────
  const handleMouseDown = () => {
    isResizingRef.current = true;
    document.body.style.cursor = 'col-resize';
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return;
      const newWidth = window.innerWidth - e.clientX;
      setHudWidth(Math.max(280, Math.min(newWidth, 750)));
    };

    const handleMouseUp = () => {
      if (isResizingRef.current) {
        isResizingRef.current = false;
        document.body.style.cursor = '';
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // ── Conversation sorting/filtering & Date Grouping ──────────────
  const filteredChats = chats.filter((c) => !searchQuery || (c.title || '').toLowerCase().includes(searchQuery.toLowerCase()));

  const pinnedList = filteredChats.filter((c) => pinnedChats.includes(c.id) && !archivedChats.includes(c.id));
  const unpinnedList = filteredChats.filter((c) => !pinnedChats.includes(c.id) && !archivedChats.includes(c.id));

  const { today: todayList, yesterday: yesterdayList, last7Days: last7DaysList, older: olderList } = groupChatsByDate(unpinnedList);

  // ── Export ───────────────────────────────────────────────────
  const handleExport = (format: 'pdf' | 'markdown' | 'json' | 'text') => {
    const visible = messages.filter((m) => m.role !== 'system' && m.role !== 'tool');
    const title   = chats.find((c) => c.id === activeChatId)?.title || 'Chat Export';
    let content = ''; let filename = ''; let mimeType = '';

    if (format === 'pdf') {
      const printWindow = window.open('', '_blank');
      if (!printWindow) return;

      const formattedDate = new Date().toLocaleString();

      const escapeHtml = (str: string) =>
        str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

      const formatContent = (text: string) => {
        let html = escapeHtml(text);
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
          return `<pre><code>${code.trim()}</code></pre>`;
        });
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
        html = html.replace(/\n\n/g, '</p><p>');
        html = html.replace(/\n/g, '<br/>');
        return `<p>${html}</p>`;
      };

      const htmlContent = `
        <!DOCTYPE html>
        <html>
          <head>
            <meta charset="utf-8" />
            <title>${escapeHtml(title)} - PDF Export</title>
            <style>
              @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');
              @page {
                size: A4;
                margin: 15mm;
              }
              * { box-sizing: border-box; }
              body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                color: #0f172a;
                background: #ffffff;
                line-height: 1.6;
                font-size: 13px;
                padding: 24px;
                margin: 0;
              }
              .header {
                border-bottom: 2px solid #e2e8f0;
                padding-bottom: 16px;
                margin-bottom: 24px;
              }
              .brand {
                font-size: 11px;
                font-weight: 700;
                color: #2563eb;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                margin-bottom: 4px;
              }
              .title {
                font-size: 22px;
                font-weight: 700;
                color: #0f172a;
                margin: 0 0 8px 0;
              }
              .meta {
                font-size: 11px;
                color: #64748b;
              }
              .message {
                margin-bottom: 20px;
                padding: 16px 20px;
                border-radius: 12px;
                page-break-inside: avoid;
              }
              .message.user {
                background-color: #f1f5f9;
                border-left: 4px solid #3b82f6;
              }
              .message.assistant {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-left: 4px solid #10b981;
              }
              .role {
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-bottom: 8px;
              }
              .role.user { color: #2563eb; }
              .role.assistant { color: #059669; }
              .content p { margin: 0 0 10px 0; }
              .content p:last-child { margin-bottom: 0; }
              h1, h2, h3 { color: #0f172a; margin-top: 16px; margin-bottom: 8px; }
              h1 { font-size: 18px; }
              h2 { font-size: 16px; }
              h3 { font-size: 14px; }
              pre {
                background: #0f172a;
                color: #f8fafc;
                padding: 12px 16px;
                border-radius: 8px;
                font-family: 'Fira Code', monospace;
                font-size: 12px;
                overflow-x: auto;
                white-space: pre-wrap;
                word-break: break-all;
                margin: 12px 0;
              }
              code {
                font-family: 'Fira Code', monospace;
                background: #e2e8f0;
                color: #0f172a;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 12px;
              }
              pre code {
                background: transparent;
                padding: 0;
                color: inherit;
              }
              @media print {
                body { padding: 0; }
                .message { page-break-inside: avoid; }
              }
            </style>
          </head>
          <body>
            <div class="header">
              <div class="brand">Omni AI Chatbot</div>
              <h1 class="title">${escapeHtml(title)}</h1>
              <div class="meta">Exported: ${formattedDate}</div>
            </div>
            ${visible.map((m) => `
              <div class="message ${m.role}">
                <div class="role ${m.role}">${m.role === 'user' ? 'You' : 'Assistant'}</div>
                <div class="content">${formatContent(m.content)}</div>
              </div>
            `).join('')}
            <script>
              window.onload = function() {
                setTimeout(function() {
                  window.print();
                }, 300);
              };
            </script>
          </body>
        </html>
      `;

      printWindow.document.write(htmlContent);
      printWindow.document.close();
      return;
    }

    if (format === 'markdown') {
      content  = `# ${title}\n\n*Exported: ${new Date().toLocaleString()}*\n\n---\n\n`;
      visible.forEach((m) => {
        content += m.role === 'user' ? `**You:**\n${m.content}\n\n---\n\n` : `**Assistant:**\n${m.content}\n\n---\n\n`;
      });
      filename = `chat-${Date.now()}.md`; mimeType = 'text/markdown';
    } else if (format === 'json') {
      content  = JSON.stringify({ title, exported_at: new Date().toISOString(), messages: visible }, null, 2);
      filename = `chat-${Date.now()}.json`; mimeType = 'application/json';
    } else {
      content  = `${title}\nExported: ${new Date().toLocaleString()}\n\n`;
      visible.forEach((m) => { content += `${m.role === 'user' ? 'You' : 'Assistant'}:\n${m.content}\n\n`; });
      filename = `chat-${Date.now()}.txt`; mimeType = 'text/plain';
    }

    const blob = new Blob([content], { type: mimeType });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="h-full w-full flex overflow-hidden relative"
      role="main"
    >
      {/* Toast container — sits above everything */}
      <ToastContainer toasts={toasts} onRemove={removeToast} />

      {/* Keyboard shortcuts & global search modals */}
      <KeyboardShortcutsModal open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
      <GlobalSearch open={globalSearchOpen} onClose={() => setGlobalSearchOpen(false)} chats={chats} onSelectChat={(id) => { setActiveChatId(id); navigate(`/c/${id}`); }} />

      {/* ══════════ CONVERSATION SIDEBAR ══════════ */}
      <aside
        className="flex flex-col border-r border-border/80 bg-surface flex-shrink-0 sidebar-transition hidden lg:flex select-none"
        style={{ width: convoOpen ? '280px' : '58px' }}
        aria-label="Conversations"
      >
        {convoOpen ? (
          <>
            {/* Top Area: Header, New Chat, Quick Features */}
            <div className="p-3 space-y-2 flex-shrink-0 bg-surface">
              {/* Header: Omni Branding Logo & Search / Collapse controls */}
              <div className="flex items-center justify-between px-1 py-1">
                <Tooltip content="Omni AI" side="bottom">
                  <button onClick={() => setConvoOpen(true)} className="flex items-center gap-2 outline-none">
                    <Logo size={22} collapsed />
                  </button>
                </Tooltip>

                <div className="flex items-center gap-0.5">
                  <Tooltip content="Search conversations" side="bottom">
                    <button
                      onClick={() => {
                        const inputEl = document.querySelector('input[placeholder="Search conversations..."]') as HTMLInputElement;
                        inputEl?.focus();
                      }}
                      className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all duration-150"
                      aria-label="Search"
                    >
                      <Search className="w-4 h-4" />
                    </button>
                  </Tooltip>

                  <Tooltip content="Collapse sidebar" side="bottom">
                    <button
                      onClick={() => setConvoOpen(false)}
                      className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all duration-150"
                      aria-label="Collapse"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                  </Tooltip>
                </div>
              </div>

              {/* New Chat Button */}
              <button
                onClick={handleCreateChat}
                className="w-full flex items-center justify-between px-3 py-2.5 rounded-[14px] bg-surface-2 hover:bg-surface-3 text-foreground text-sm font-semibold transition-all duration-150 active:scale-[0.98] border border-border/60 shadow-sm"
              >
                <div className="flex items-center gap-2.5">
                  <Pencil className="w-4 h-4 text-foreground-2" />
                  <span>New chat</span>
                </div>
              </button>

              {/* Inline Search Input */}
              <div className="relative w-full pt-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-3 pointer-events-none" />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search conversations..."
                  className="w-full bg-surface-2/80 border border-border/60 hover:border-border focus:border-accent/40 rounded-[12px] pl-9 pr-7 py-1.5 text-xs text-foreground placeholder:text-foreground-3/70 focus:outline-none transition-all duration-150"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 rounded-full text-foreground-3 hover:text-foreground"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>

              {/* Omni Quick Navigation Features */}
              <div className="space-y-0.5 pt-1">
                <button
                  onClick={() => setFilesModalOpen(true)}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150 text-left"
                >
                  <FolderClosed className="w-4 h-4 text-foreground-3" />
                  <span>Workspace Files</span>
                </button>

                <button
                  onClick={toggleDeveloperMode}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150 text-left"
                >
                  <Terminal className="w-4 h-4 text-foreground-3" />
                  <span>Developer HUD</span>
                  {developerMode && (
                    <span className="text-[9px] font-bold text-accent uppercase bg-accent/10 px-1.5 py-0.5 rounded-full ml-auto">
                      ON
                    </span>
                  )}
                </button>
              </div>
            </div>

            {/* Conversation List Container */}
            <div className="flex-1 overflow-y-auto scrollbar-hide py-2">
              {/* Group: Pinned */}
              {pinnedList.length > 0 && (
                <div className="mb-3">
                  <div className="px-3 pt-1 pb-1 text-[11px] font-semibold text-foreground-2 opacity-80 select-none">
                    Pinned
                  </div>
                  <div className="space-y-0.5 px-2 mt-0.5">
                    {pinnedList.map((c) => renderChatRow(c, true))}
                  </div>
                </div>
              )}

              {/* Group: Today */}
              {todayList.length > 0 && (
                <div className="mb-3">
                  <div className="px-3 pt-1 pb-1 text-[11px] font-semibold text-foreground-2 opacity-80 select-none">
                    Today
                  </div>
                  <div className="space-y-0.5 px-2 mt-0.5">
                    {todayList.map((c) => renderChatRow(c))}
                  </div>
                </div>
              )}

              {/* Group: Yesterday */}
              {yesterdayList.length > 0 && (
                <div className="mb-3">
                  <div className="px-3 pt-1 pb-1 text-[11px] font-semibold text-foreground-2 opacity-80 select-none">
                    Yesterday
                  </div>
                  <div className="space-y-0.5 px-2 mt-0.5">
                    {yesterdayList.map((c) => renderChatRow(c))}
                  </div>
                </div>
              )}

              {/* Group: Last 7 Days */}
              {last7DaysList.length > 0 && (
                <div className="mb-3">
                  <div className="px-3 pt-1 pb-1 text-[11px] font-semibold text-foreground-2 opacity-80 select-none">
                    Last 7 Days
                  </div>
                  <div className="space-y-0.5 px-2 mt-0.5">
                    {last7DaysList.map((c) => renderChatRow(c))}
                  </div>
                </div>
              )}

              {/* Group: Older */}
              {olderList.length > 0 && (
                <div className="mb-3">
                  <div className="px-3 pt-1 pb-1 text-[11px] font-semibold text-foreground-2 opacity-80 select-none">
                    Older
                  </div>
                  <div className="space-y-0.5 px-2 mt-0.5">
                    {olderList.map((c) => renderChatRow(c))}
                  </div>
                </div>
              )}

              {filteredChats.length === 0 && (
                <div className="py-12 text-center text-foreground-3 text-xs">
                  {searchQuery ? 'No conversations found' : 'No conversations yet'}
                </div>
              )}
            </div>
          </>
        ) : (
          /* Collapsed state — clean, compact toolbar without vertical list of chat icons */
          <div className="flex-1 flex flex-col items-center py-3 px-1.5 gap-3">
            <Tooltip content="Expand Sidebar" side="right">
              <button
                onClick={() => setConvoOpen(true)}
                className="p-2 rounded-xl text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all duration-150"
                aria-label="Expand"
              >
                <Logo size={22} collapsed />
              </button>
            </Tooltip>

            <Tooltip content="New Chat" side="right">
              <button
                onClick={handleCreateChat}
                aria-label="New Chat"
                className="w-9 h-9 rounded-xl flex items-center justify-center bg-surface-2 text-foreground hover:bg-surface-3 border border-border/60 transition-all duration-150"
              >
                <Plus className="w-4 h-4" />
              </button>
            </Tooltip>

            <Tooltip content="Workspace Files" side="right">
              <button
                onClick={() => setFilesModalOpen(true)}
                aria-label="Files"
                className="w-9 h-9 rounded-xl flex items-center justify-center text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all duration-150"
              >
                <FolderClosed className="w-4 h-4" />
              </button>
            </Tooltip>

            <Tooltip content="Developer HUD" side="right">
              <button
                onClick={toggleDeveloperMode}
                aria-label="Dev HUD"
                className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-150 ${
                  developerMode ? 'bg-accent/10 text-accent border border-accent/20' : 'text-foreground-3 hover:text-foreground hover:bg-surface-2'
                }`}
              >
                <Terminal className="w-4 h-4" />
              </button>
            </Tooltip>
          </div>
        )}

        {/* Footer: User account section at bottom */}
        <div className="border-t border-border/60 p-2 flex-shrink-0 bg-surface">
          <div className="relative w-full">
            <Tooltip content={!convoOpen ? (user?.full_name || user?.email || 'Account') : undefined} side="right">
              <button
                onClick={() => setShowUserMenu(!showUserMenu)}
                aria-label="User menu"
                aria-expanded={showUserMenu}
                className={`w-full flex items-center justify-between rounded-[14px] transition-all duration-150 hover:bg-surface-2
                  ${convoOpen ? 'px-2.5 py-2' : 'p-2 justify-center'}`}
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  {/* Avatar */}
                  <div className="w-8 h-8 rounded-full bg-surface-3 border border-border-2 flex items-center justify-center text-foreground font-bold text-xs flex-shrink-0 select-none shadow-sm">
                    {userInitial}
                  </div>
                  {convoOpen && (
                    <div className="min-w-0 flex-1 text-left">
                      <p className="text-xs font-semibold truncate leading-tight text-foreground">{user?.full_name || 'User'}</p>
                      <p className="text-[10px] text-foreground-3 truncate leading-none mt-0.5">{user?.email || 'Account'}</p>
                    </div>
                  )}
                </div>

                {convoOpen && (
                  <MoreHorizontal className="w-4 h-4 text-foreground-3 flex-shrink-0" />
                )}
              </button>
            </Tooltip>

            {/* User Dropdown menu */}
            {showUserMenu && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
                <div
                  className={`absolute ${convoOpen ? 'left-0' : 'left-full ml-2'} bottom-full mb-2 w-48 bg-surface border border-border-2 rounded-2xl shadow-2xl p-1.5 z-50 animate-scale-in space-y-0.5`}
                  style={{ animationDuration: '180ms' }}
                >
                  <button
                    onClick={() => { navigate('/settings'); setShowUserMenu(false); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150"
                  >
                    <Settings className="w-4 h-4 text-foreground-3" />
                    <span>Settings</span>
                  </button>
                  <div className="my-1 border-t border-border/60" />
                  <button
                    onClick={() => { logout(); navigate('/login'); setShowUserMenu(false); }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 transition-all duration-150"
                  >
                    <LogOut className="w-4 h-4 text-rose-400" />
                    <span>Logout</span>
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* ══════════ MAIN CHAT ══════════ */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative bg-background">

        {/* Toolbar */}
        <header className="h-[var(--header-height)] px-4 flex items-center justify-between bg-background flex-shrink-0 z-10">
          <div className="flex items-center gap-2.5 min-w-0">
            <button onClick={() => setConvoOpen((v) => !v)} className="lg:hidden p-1.5 text-foreground-3 hover:text-foreground">
              <MessageSquare className="w-4 h-4" />
            </button>
            {/* Model Dropdown Selection (Top Left) */}
            <div className="relative">
              <button 
                onClick={() => setModelDropdownOpen((v) => !v)}
                className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-border bg-surface-2/65 hover:bg-surface-3 hover:border-accent/35 text-xs font-semibold text-foreground transition-all duration-150 active:scale-[0.97] outline-none"
              >
                {currentModel.icon && <currentModel.icon className="w-3 h-3 text-accent" />}
                <span className="truncate max-w-[100px] sm:max-w-[150px]">{currentModel.name || 'Select Model'}</span>
                <ChevronDown className="w-3.5 h-3.5 text-foreground-3" />
              </button>
              {modelDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setModelDropdownOpen(false)} />
                  <div className="absolute left-0 top-full mt-1.5 w-64 max-h-[300px] overflow-y-auto bg-surface border border-border-2 rounded-2xl shadow-2xl p-1.5 z-50 animate-scale-in space-y-0.5">
                    <div className="px-2 py-1 text-[9px] font-bold text-foreground-3 uppercase tracking-wider">
                      Verified Keys Models
                    </div>
                    {models.length === 0 ? (
                      <div className="px-2 py-2 text-xs text-foreground-3 italic">
                        No verified API keys. Add in Settings.
                      </div>
                    ) : (
                      models.map((m) => {
                        const IconComponent = m.icon;
                        const isSelected = m.id === activeModel;
                        return (
                          <button
                            key={m.id}
                            onClick={() => {
                              setActiveModel(m.id);
                              setModelDropdownOpen(false);
                            }}
                            className={`w-full flex flex-col items-start px-2.5 py-1.5 rounded-xl text-left transition-all duration-150 ${
                              isSelected 
                                ? 'bg-accent/10 text-accent font-semibold' 
                                : 'text-foreground hover:bg-surface-2'
                            }`}
                          >
                            <div className="flex items-center gap-1.5 w-full">
                              {IconComponent && <IconComponent className={`w-3.5 h-3.5 ${isSelected ? 'text-accent' : 'text-foreground-3'}`} />}
                              <span className="text-xs truncate flex-1">{m.name}</span>
                              {isSelected && <Check className="w-3 h-3 text-accent" />}
                            </div>
                            <span className="text-[8px] text-foreground-3 font-medium uppercase tracking-wide mt-0.5">{m.provider}</span>
                          </button>
                        );
                      })
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">

            {/* Questions hover popup button */}
            {messages.filter((m) => m.role === 'user').length > 0 && (
              <div
                className="questions-popup-wrap"
                onMouseEnter={() => {
                  if (popupLeaveTimer.current) { clearTimeout(popupLeaveTimer.current); popupLeaveTimer.current = null; }
                  setQuestionsPopupOpen(true);
                }}
                onMouseLeave={() => {
                  popupLeaveTimer.current = setTimeout(() => setQuestionsPopupOpen(false), 150);
                }}
              >
                <button
                  className={`flex items-center justify-center w-8 h-8 rounded-lg border text-xs font-semibold shadow-sm transition-all duration-150 ${
                    questionsPopupOpen
                      ? 'border-accent/40 bg-accent/15 text-accent'
                      : 'border-border/85 bg-surface-2/65 text-foreground-2 hover:text-foreground hover:bg-surface-3 hover:border-accent/35'
                  }`}
                  aria-label="Questions Navigator"
                >
                  <ListOrdered className="w-4 h-4" />
                </button>

                {questionsPopupOpen && (
                  <div className="questions-popup">
                    <div className="questions-popup-header">Follow-ups</div>
                    <div className="questions-popup-list">
                      {userQuestions.map((q) => (
                        <button
                          key={q.id}
                          className={`questions-popup-item ${highlightedMsgId === q.id ? 'active' : ''}`}
                          onClick={() => {
                            jumpToMessage(q.id);
                            setQuestionsPopupOpen(false);
                          }}
                        >
                          <span className="questions-popup-item-num">{q.index}</span>
                          <span className="questions-popup-item-text">{q.content}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Single three-dot dropdown — contains Dev HUD, Share, Export, and chat actions */}
            {activeChat && (
              <div className="relative">
                <Tooltip content="More options" side="bottom">
                  <button onClick={() => setMenuOpen((v) => !v)}
                    className={`flex items-center justify-center w-8 h-8 rounded-lg border text-xs font-semibold shadow-sm hover:shadow-md hover:shadow-black/20 hover:scale-[1.03] active:scale-[0.97] transition-all duration-150 ${
                      menuOpen 
                        ? 'border-accent/40 bg-accent/15 text-accent shadow-accent/5' 
                        : 'border-border/85 bg-surface-2/65 text-foreground-2 hover:text-foreground hover:bg-surface-3 hover:border-accent/35'
                    }`}
                    aria-label="More actions">
                    <MoreHorizontal className="w-4 h-4" />
                  </button>
                </Tooltip>

                {menuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
                    <div className="absolute right-0 top-full mt-1.5 w-72 bg-surface border border-border-2 rounded-2xl shadow-2xl p-1.5 z-50 animate-scale-in space-y-0.5">

                      {/* ── Dev HUD ── */}
                      <button onClick={() => { toggleDeveloperMode(); setMenuOpen(false); }}
                        className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left text-xs font-medium transition-all duration-150 ${
                          developerMode
                            ? 'text-accent bg-accent/10 hover:bg-accent/15'
                            : 'text-foreground-2 hover:text-foreground hover:bg-surface-2'
                        }`}>
                        <Terminal className="w-4 h-4 text-foreground-3" />
                        <span className="flex-1">Developer HUD</span>
                        {developerMode && <span className="text-[9px] font-bold text-accent uppercase bg-accent/10 px-1.5 py-0.5 rounded-full">ON</span>}
                      </button>

                      <div className="h-[1px] bg-border/60 my-1" />

                      {/* ── Share panel ── */}
                      <div className="px-3 py-2.5 space-y-3">
                        <div className="flex items-center gap-2">
                          <Share2 className="w-3.5 h-3.5 text-foreground-3" />
                          <span className="text-xs font-semibold text-foreground">Share conversation</span>
                        </div>

                        {/* Static share toggle */}
                        <div className="space-y-2">
                          <div className="flex items-center justify-between py-1.5 px-3 rounded-xl bg-surface-2 border border-border">
                            <div>
                              <div className="text-[10px] font-medium text-foreground-2">Enable public link</div>
                              <div className="text-[9px] text-foreground-3">Snapshot of current messages</div>
                            </div>
                            <button type="button" onClick={() => handleToggleShare(activeChat.id, !activeChat.is_shared, false)}
                              className={`w-8 h-4 rounded-full transition-colors relative flex items-center ${
                                activeChat.is_shared && !activeChat.is_live_share ? 'bg-accent' : 'bg-surface-3'
                              }`}>
                              <span className={`w-3.5 h-3.5 rounded-full bg-white transition-transform ${
                                activeChat.is_shared && !activeChat.is_live_share ? 'translate-x-4' : 'translate-x-0.5'
                              }`} />
                            </button>
                          </div>

                          {/* Live share toggle */}
                          <div className="flex items-center justify-between py-1.5 px-3 rounded-xl bg-surface-2 border border-border">
                            <div>
                              <div className="flex items-center gap-1.5">
                                <div className="text-[10px] font-medium text-foreground-2">Live share</div>
                                <span className="text-[8px] font-bold text-emerald-400 uppercase bg-emerald-400/10 px-1.5 py-0.5 rounded-full">New</span>
                              </div>
                              <div className="text-[9px] text-foreground-3">Viewers see future messages too</div>
                            </div>
                            <button type="button" onClick={() => handleToggleShare(activeChat.id, !activeChat.is_live_share, !activeChat.is_live_share)}
                              className={`w-8 h-4 rounded-full transition-colors relative flex items-center ${
                                activeChat.is_live_share ? 'bg-emerald-500' : 'bg-surface-3'
                              }`}>
                              <span className={`w-3.5 h-3.5 rounded-full bg-white transition-transform ${
                                activeChat.is_live_share ? 'translate-x-4' : 'translate-x-0.5'
                              }`} />
                            </button>
                          </div>
                        </div>

                        {/* Shareable link — shown when either share mode is active */}
                        {activeChat.is_shared && activeChat.share_id && (
                          <div className="space-y-1 animate-slide-up">
                            <div className="flex items-center gap-1">
                              {activeChat.is_live_share
                                ? <><div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /><span className="text-[9px] text-emerald-400 font-semibold">LIVE</span></>
                                : <><Lock className="w-3 h-3 text-amber-400" /><span className="text-[9px] text-amber-400 font-semibold">SNAPSHOT</span></>
                              }
                            </div>
                            <div className="flex gap-1.5">
                              <input readOnly value={`${window.location.origin}/share/${activeChat.share_id}`}
                                className="flex-1 bg-surface-2 border border-border rounded-lg px-2 py-1 text-[10px] text-foreground font-mono focus:outline-none" />
                              <button onClick={() => {
                                navigator.clipboard.writeText(`${window.location.origin}/share/${activeChat.share_id}`);
                                setCopiedShareLink(true);
                                setTimeout(() => setCopiedShareLink(false), 2000);
                              }} className="px-2.5 py-1 bg-accent text-white rounded-lg text-[10px] font-semibold flex items-center gap-1">
                                {copiedShareLink ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                                {copiedShareLink ? 'Copied' : 'Copy'}
                              </button>
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="h-[1px] bg-border/60 my-1" />

                      {/* ── Export ── */}
                      {messages.filter((m) => m.role !== 'system').length > 0 && (
                        <>
                          <button onClick={() => { setMenuOpen(false); handleExport('pdf'); }}
                            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150">
                            <Download className="w-4 h-4 text-foreground-3" />
                            <span className="flex-1">Export as PDF</span>
                            <span className="text-[9px] text-foreground-3">.pdf</span>
                          </button>
                          <button onClick={() => { setMenuOpen(false); handleExport('markdown'); }}
                            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150">
                            <FileText className="w-4 h-4 text-foreground-3" />
                            <span className="flex-1">Export as Markdown</span>
                            <span className="text-[9px] text-foreground-3">.md</span>
                          </button>
                          <button onClick={() => { setMenuOpen(false); handleExport('json'); }}
                            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150">
                            <FileJson className="w-4 h-4 text-foreground-3" />
                            <span className="flex-1">Export as JSON</span>
                            <span className="text-[9px] text-foreground-3">.json</span>
                          </button>
                          <div className="h-[1px] bg-border/60 my-1" />
                        </>
                      )}

                      {/* ── Chat actions ── */}
                      <button onClick={() => { setMenuOpen(false); setFilesModalOpen(true); }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150">
                        <Files className="w-4 h-4 text-foreground-3" />
                        <span className="flex-1">View files in chat</span>
                        {chatDocuments.length > 0 && (
                          <span className="bg-accent/15 text-accent px-1.5 py-0.5 rounded-full text-[9px] font-semibold border border-accent/20">
                            {chatDocuments.length}
                          </span>
                        )}
                      </button>

                      <button onClick={() => { setMenuOpen(false); togglePinChat(activeChat.id); }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150">
                        <Pin className={`w-4 h-4 text-foreground-3 ${pinnedChats.includes(activeChat.id) ? 'fill-foreground-3' : ''}`} />
                        <span>{pinnedChats.includes(activeChat.id) ? 'Unpin chat' : 'Pin chat'}</span>
                      </button>

                      <button onClick={() => { setMenuOpen(false); toggleArchiveChat(activeChat.id); }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150">
                        <Archive className="w-4 h-4 text-foreground-3" />
                        <span>{archivedChats.includes(activeChat.id) ? 'Unarchive' : 'Archive'}</span>
                      </button>

                      <div className="h-[1px] bg-border/60 my-1" />

                      <button onClick={() => { setMenuOpen(false); handleDeleteChat(activeChat.id); }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left text-xs font-semibold text-red-500 hover:text-red-400 hover:bg-red-500/10 transition-all duration-150">
                        <Trash2 className="w-4 h-4" />
                        <span>Delete</span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>



        </header>

        {messagesLoading ? (
          /* ── LOADING STATE: skeleton while fetching history ── */
          <div className="flex-1 overflow-y-auto px-4 py-8">
            <div className="max-w-chat mx-auto space-y-6">
              {[...Array(5)].map((_, i) => (
                <div key={i} className={`flex items-end gap-3 ${i % 2 === 0 ? 'justify-end' : 'justify-start'}`}>
                  {i % 2 !== 0 && <div className="w-8 h-8 rounded-xl bg-surface-2 animate-pulse flex-shrink-0" />}
                  <div
                    className="rounded-2xl bg-surface-2 animate-pulse"
                    style={{ width: `${140 + (i * 53) % 180}px`, height: `${36 + (i * 17) % 28}px`, animationDelay: `${i * 80}ms` }}
                  />
                  {i % 2 === 0 && <div className="w-8 h-8 rounded-xl bg-surface-2 animate-pulse flex-shrink-0" style={{ animationDelay: `${i * 80}ms` }} />}
                </div>
              ))}
            </div>
          </div>
        ) : messages.length === 0 ? (
          /* ── EMPTY STATE: welcome + centered input ── */
          <div className="flex-1 flex flex-col items-center justify-center px-4 py-8 overflow-y-auto relative">
            {/* Ambient glow orbs */}
            <div className="welcome-orb welcome-orb-1" aria-hidden />
            <div className="welcome-orb welcome-orb-2" aria-hidden />
            <div className="w-full max-w-chat flex flex-col items-center gap-10 relative z-10">
              <div className="welcome-content">
                <div className="welcome-logo-ring" aria-hidden>
                  <Logo size={28} collapsed />
                </div>
                <h2 className="welcome-headline">{greeting.headline}</h2>
                <p className="welcome-sub">{greeting.sub}</p>
              </div>

              {/* Centered input form */}
              <ChatInput
                onSend={(text, images) => handleSendMessage(text, images)}
                isLocked={isLocked}
                isStreaming={isStreaming}
                onStop={handleStopGeneration}
                activeModel={activeModel}
                onOpenShortcuts={() => setShortcutsOpen(true)}
                placeholder="Message Omni…"
                className="w-full"
                chats={chats}
                connectedChat={connectedChat}
                onSelectConnectedChat={setConnectedChat}
              />
            </div>
          </div>
        ) : (
          /* ── CHAT STATE: scrollable messages + bottom footer ── */
          <>
            <div ref={chatScrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto px-4 py-8 space-y-6" style={{ scrollBehavior: 'smooth' }}>
              <div className="max-w-chat mx-auto space-y-5">


              {messages.map((m, idx) => {
                if (m.role === 'system' || m.role === 'tool') return null;
                const isUser          = m.role === 'user';
                const isLastAsst      = !isUser && idx === messages.length - 1;
                const isStreamingThis = isStreaming && isLastAsst && m.content === '';
                const isEditing       = editingMsgId === m.id;
                // SOURCE ATTRIBUTION FIX:
                // Read from `source_documents` (CRAG-validated, used=true only)
                // NOT from `retrieved_context` (which contains ALL retrieved chunks
                // including ones rejected by CRAG or below the similarity threshold).
                // Bug: previously showed Resume.pdf/Aptitude.pdf for 'LeetCode 23'
                // because retrieved_context had all chunks regardless of relevance.
                const sources: SourceDocument[] = !isUser
                  ? (m.developer_metrics?.source_documents?.filter(s => s.used !== false) ?? [])
                  : [];

                const responseMeta = !isUser && !isStreamingThis ? getResponseMeta(m.content) : null;

                return (
                  <div
                    key={m.id}
                    ref={(el) => { messageRefs.current[m.id] = el; }}
                    className={`flex gap-4 group/msg animate-message-in ${isUser ? 'justify-end' : 'justify-start'} message-gap ${
                      highlightedMsgId === m.id ? 'message-highlight' : ''
                    }`}
                  >
                    <div className={`max-w-[85%] flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
                      {/* User message block */}
                      {isUser && (
                        isEditing ? (
                          <div className="w-full min-w-[280px] space-y-2">
                            <textarea ref={editTextareaRef} value={editValue} onChange={(e) => setEditValue(e.target.value)}
                              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmitEdit(m.id); } if (e.key === 'Escape') handleCancelEdit(); }}
                              rows={Math.max(2, editValue.split('\n').length)}
                              className="w-full rounded-xl px-3.5 py-2.5 text-sm text-foreground bg-surface border border-accent/40 focus:outline-none focus:ring-1 focus:ring-accent resize-none leading-relaxed"
                              style={{ minHeight: '72px', maxHeight: '240px' }} />
                            <div className="flex items-center gap-1.5 justify-end">
                              <button onClick={handleCancelEdit} className="px-3 py-1.5 rounded-lg text-[11px] font-medium text-foreground-3 hover:text-foreground bg-surface-2 hover:bg-surface-3 border border-border transition-all">Cancel</button>
                              <button onClick={() => handleSubmitEdit(m.id)} disabled={!editValue.trim()}
                                className="px-3 py-1.5 rounded-lg text-[11px] font-semibold text-white bg-accent hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1.5">
                                <Send className="w-3 h-3" /> Send
                              </button>
                            </div>
                          </div>
                        ) : (() => {
                          const { prompt: userPrompt, files: userAttachedFiles, refTitle } = parseUserMessageFiles(m.content);
                          return (
                            <div className="user-bubble rounded-2xl rounded-tr-sm px-4 py-3 text-sm flex flex-col gap-2">
                              {refTitle && (
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/10 border border-white/15 text-[11px] font-medium text-white/90 mb-0.5 w-fit">
                                  <Link className="w-3 h-3 text-white/70" />
                                  <span>Reference: <strong className="font-semibold text-white">{refTitle}</strong></span>
                                </div>
                              )}
                              {m.imagePreviewUrls && m.imagePreviewUrls.length > 0 && (
                                <div className="flex flex-wrap gap-1.5 mb-1">
                                  {m.imagePreviewUrls.map((url, idx) => (
                                    <img key={idx} src={url} alt="attached image" className="max-w-[200px] max-h-[150px] rounded-lg object-contain border border-white/10" />
                                  ))}
                                </div>
                              )}
                              {userAttachedFiles.length > 0 && (
                                <div className="flex flex-col gap-2 my-1">
                                  {userAttachedFiles.map((file, fIdx) => (
                                    <div key={fIdx} className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-white/10 border border-white/15">
                                      <div className="flex items-center gap-2 min-w-0">
                                        <FileText className="w-4 h-4 text-white/90" />
                                        <div className="min-w-0">
                                          <p className="text-xs font-semibold text-white truncate">{file.name}</p>
                                          <p className="text-[10px] text-white/70">{file.content.length.toLocaleString()} chars</p>
                                        </div>
                                      </div>
                                      <button
                                        type="button"
                                        onClick={() => setSelectedUserFile(file)}
                                        className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-white/20 hover:bg-white/30 text-white transition-all flex items-center gap-1"
                                      >
                                        View File
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              )}
                              {userPrompt && <p className="whitespace-pre-wrap break-words leading-relaxed text-foreground">{userPrompt}</p>}
                            </div>
                          );
                        })()
                      )}

                      {/* Assistant message block */}
                      {!isUser && (() => {
                        if (isStreamingThis) return <TypingIndicator />;
                        const { clean, error } = parseErrorFromContent(m.content);
                        // Pure error — no real content
                        if (!clean && error) return (
                          <div className="assistant-bubble text-foreground rounded-2xl rounded-bl-sm px-4 py-3 text-sm w-full">
                            <ErrorCard message={error} onRetry={() => {
                              const lastUser = [...messages].reverse().find(x => x.role === 'user');
                              if (lastUser) handleSendMessage(lastUser.content);
                            }} />
                          </div>
                        );
                        return (
                          <div className="assistant-bubble text-foreground rounded-2xl rounded-bl-sm px-4 py-3 text-sm w-full">
                            {/* Response meta bar — premium editorial style */}
                            {responseMeta?.isLong && !isStreaming && (
                              <div className="response-meta-bar">
                                <span className="response-meta-dot" />
                                <span className="response-meta-text">
                                  {responseMeta.words.toLocaleString()} words
                                </span>
                                <span className="response-meta-sep">&middot;</span>
                                <span className="response-meta-text">
                                  {responseMeta.readTime}
                                </span>
                                {responseMeta.sections > 0 && (
                                  <>
                                    <span className="response-meta-sep">&middot;</span>
                                    <span className="response-meta-text">
                                      {responseMeta.sections} section{responseMeta.sections !== 1 ? 's' : ''}
                                    </span>
                                  </>
                                )}
                              </div>
                            )}
                            <CitedContent
                              content={clean || m.content}
                              sources={sources}
                              isStreaming={isStreaming && isLastAsst && m.content !== ''}
                            />
                            {error && <ErrorCard message={error} onRetry={() => {
                              const lastUser = [...messages].reverse().find(x => x.role === 'user');
                              if (lastUser) handleSendMessage(lastUser.content);
                            }} />}
                          </div>
                        );
                      })()}

                      {/* Action trigger bars */}
                      <div className="message-action-bar mt-1">
                        {isUser && !isEditing && (
                          <>
                            <ActionBtn icon={copiedMsgId === m.id ? Check : Copy} label={copiedMsgId === m.id ? 'Copied' : 'Copy'} onClick={() => handleCopyMessage(m.id, m.content)} active={copiedMsgId === m.id} />
                            <ActionBtn icon={Pencil} label="Edit" onClick={() => handleStartEdit(m.id, m.content)} />
                            <ActionBtn icon={Trash2} label="Delete" danger onClick={() => handleDeleteMessage(m.id)} />
                          </>
                        )}
                        {!isUser && m.content && !isStreamingThis && (
                          <>
                            <ActionBtn icon={copiedMsgId === m.id ? Check : Copy} label={copiedMsgId === m.id ? 'Copied' : 'Copy'} onClick={() => handleCopyMessage(m.id, m.content)} active={copiedMsgId === m.id} />
                            <div className="w-px h-3.5 bg-border mx-0.5" />
                            <ActionBtn icon={RefreshCw} label="Regenerate" onClick={() => handleRetry(idx)} />
                            <div className="w-px h-3.5 bg-border mx-0.5" />
                            <ActionBtn icon={GitBranch} label="Branch in new chat" onClick={() => {
                              if (activeChat) {
                                setConnectedChat({ id: activeChat.id, title: activeChat.title || 'Untitled Chat' });
                                handleCreateChat();
                              }
                            }} />
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              </div>
              <div ref={messagesEndRef} />
            </div>

            {/* Chat Minimap — outside scroll area, fixed to right edge of chat column */}
            {messages.filter((m) => m.role !== 'system' && m.role !== 'tool').length > 3 && (() => {
              const visibleMsgs = messages.filter((m) => m.role !== 'system' && m.role !== 'tool');
              const total = visibleMsgs.length;
              return (
                <div
                  className="chat-minimap"
                  aria-hidden
                  onClick={handleMinimapClick}
                  style={{ bottom: '72px' }}
                >
                  <div ref={minimapTrackRef} className="chat-minimap-track" title="Click to jump">
                    {visibleMsgs.map((m, i) => (
                      <div
                        key={m.id}
                        className={`chat-minimap-dot ${m.role}`}
                        style={{ top: `${(i / total) * 100}%` }}
                      />
                    ))}
                    <div
                      className="chat-minimap-thumb"
                      style={{ top: `${minimapThumbTop}%`, height: `${minimapThumbHeight}%` }}
                    />
                  </div>
                </div>
              );
            })()}
            {showScrollBtn && (
              <button onClick={scrollToBottom}
                className="scroll-btn p-2.5 rounded-full bg-surface border border-border shadow-lg text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all animate-fade-in"
                aria-label="Scroll to bottom">
                <ArrowDown className="w-4.5 h-4.5" />
              </button>
            )}

            {/* Input Bar Footer */}
            <footer className="px-4 py-4 flex-shrink-0 border-t border-border/30 bg-gradient-to-t from-background to-background/60 backdrop-blur-sm">
              <ChatInput
                onSend={(text, images) => handleSendMessage(text, images)}
                isLocked={isLocked}
                isStreaming={isStreaming}
                onStop={handleStopGeneration}
                activeModel={activeModel}
                onOpenShortcuts={() => setShortcutsOpen(true)}
                placeholder="Message Omni…"
                className="max-w-chat mx-auto"
                chats={chats}
                connectedChat={connectedChat}
                onSelectConnectedChat={setConnectedChat}
              />
            </footer>
            {/* (Questions sidebar replaced by hover popup on toolbar button) */}
          </>
        )}
      </div>

      {/* ══════════ DEV HUD TELEMETRY PANEL ══════════ */}
      {developerMode && (
        <aside
          className="border-l border-border bg-surface flex flex-col flex-shrink-0 animate-slide-right overflow-hidden relative"
          style={{ width: hudMinimized ? '48px' : `${hudWidth}px` }}
        >
          {/* Drag resize handle */}
          {!hudMinimized && <div className="devhud-resize-handle" onMouseDown={handleMouseDown} />}

          {hudMinimized ? (
            <div className="flex-1 flex flex-col items-center py-4 px-1 gap-4 justify-between bg-surface-2">
              <div className="flex flex-col items-center gap-3">
                <button onClick={() => setHudMinimized(false)} className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-all" title="Maximize Telemetry HUD">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <div className="w-px h-6 bg-border" />
                <Terminal className="w-4 h-4 text-accent animate-pulse-ring" />
              </div>
              <div className="rotate-90 origin-center whitespace-nowrap text-[9px] font-bold uppercase tracking-widest text-foreground-3 pb-8">
                Telemetry
              </div>
            </div>
          ) : (
            <>
              <div className="h-[var(--header-height)] px-4 flex items-center justify-between flex-shrink-0 bg-surface-2">
                <div className="flex items-center gap-2"><Terminal className="w-3.5 h-3.5 text-accent" /><span className="text-xs font-semibold text-foreground">Execution Telemetry</span></div>
                <div className="flex items-center gap-1.5">
                  <Tooltip content="Minimize to bar" side="bottom">
                    <button onClick={() => setHudMinimized(true)} className="p-1 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-all" aria-label="Minimize to bar"><ChevronRight className="w-3.5 h-3.5" /></button>
                  </Tooltip>
                  <Tooltip content="Close telemetry" side="bottom">
                    <button onClick={toggleDeveloperMode} className="p-1 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-all" aria-label="Close telemetry"><X className="w-3.5 h-3.5" /></button>
                  </Tooltip>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {(() => {
                  const msg = messages.find((m) => m.id === selectedMessageId);
                  if (!msg) return (
                    <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-2">
                      <Database className="w-8 h-8 text-foreground-3/30 animate-float" />
                      <p className="text-xs text-foreground-3">Select an assistant message to inspect telemetry metrics</p>
                    </div>
                  );
                  const mx = msg.developer_metrics;
                  if (!mx) return <div className="text-center py-6 text-xs text-foreground-3">No telemetry for this response. Ensure keys are correct and active.</div>;
                  const steps   = mx.steps || ['retrieve_context', 'generate_response'];
                  const hasTool = msg.tool_calls && msg.tool_calls.length > 0;
                  return (
                    <div className="space-y-4 animate-scale-in">
                      {/* Telemetry metadata Grid */}
                      <div className="grid grid-cols-2 gap-2">
                        {[
                          { label: 'Provider',   val: currentModel.provider, color: '' },
                          { label: 'Model',      val: mx.model_used || currentModel.name,   color: '' },
                          { label: 'Latency',    val: mx.latency_ms >= 1000 ? `${(mx.latency_ms/1000).toFixed(2)}s` : `${mx.latency_ms}ms`, color: '' },
                          { label: 'Est. Cost',  val: `$${(mx.cost_estimate ?? 0).toFixed(6)}`, color: 'text-green-400' },
                          { label: 'Tokens In',  val: mx.tokens_input?.toLocaleString(),  color: '' },
                          { label: 'Tokens Out', val: mx.tokens_output?.toLocaleString(), color: '' },
                          { label: 'Mem Hits',   val: String(mx.memory_hits ?? 0), color: '' },
                          { label: 'RAG Chunks', val: String(mx.chunks_used ?? 0), color: '' },
                        ].map(({ label, val, color }) => (
                          <div key={label} className="p-2.5 rounded-xl border border-border bg-surface-2 space-y-1">
                            <span className="text-[9px] font-semibold uppercase tracking-wider text-foreground-3">{label}</span>
                            <p className={`text-xs font-bold truncate ${color || 'text-foreground'}`}>{val ?? '—'}</p>
                          </div>
                        ))}
                      </div>

                      {/* Tabs */}
                      <div className="flex border-b border-border">
                        {(['flow', 'context', 'logs'] as const).map((tab) => (
                          <button key={tab} onClick={() => setActiveHudTab(tab)}
                            className={`flex-1 pb-1.5 text-[9px] font-bold uppercase tracking-wider transition-all ${activeHudTab === tab ? 'border-b-2 border-accent text-accent' : 'text-foreground-3 hover:text-foreground border-b-2 border-transparent'}`}>
                            {tab}
                          </button>
                        ))}
                      </div>

                      {/* Tab 1: Flow / LangGraph Exec */}
                      {activeHudTab === 'flow' && (
                        <div className="pl-5 space-y-5 relative before:absolute before:left-2 before:top-1 before:bottom-1 before:w-px before:bg-border">
                          {[
                            { key: 'plan',             label: 'plan',             icon: Sparkles, detail: 'Decompose execution paths' },
                            { key: 'check_retrieval',  label: 'check_retrieval',  icon: Search,   detail: 'Self-RAG evaluation verdict' },
                            { key: 'retrieve_context', label: 'retrieve_context', icon: Database, detail: `Hits: ${mx.memory_hits ?? 0} memory / ${mx.chunks_used ?? 0} RAG chunk` },
                            { key: 'grade_documents',  label: 'grade_documents',  icon: CheckCircle2, detail: 'Document grading classification' },
                            { key: 'generate_response',label: 'generate_response',icon: Cpu,      detail: 'Processed prompt + system instructions' },
                            { key: 'execute_tools',    label: 'execute_tools',    icon: Terminal, detail: hasTool ? `${msg.tool_calls!.length} tool calls` : 'Bypassed' },
                            { key: 'reflect',          label: 'reflect',          icon: RefreshCw, detail: 'Quality score criteria check' },
                          ].map(({ key, label, icon: Icon, detail }) => {
                            const active = steps.includes(key) || (key === 'execute_tools' && hasTool);
                            return (
                              <div key={key} className="relative">
                                <div className={`absolute -left-5 w-4 h-4 rounded-full border flex items-center justify-center ${active ? 'border-accent bg-accent/10 text-accent animate-pulse-ring' : 'border-border bg-surface text-foreground-3 opacity-50'}`}>
                                  <Icon className="w-2.5 h-2.5" />
                                </div>
                                <h4 className="text-[10px] font-semibold font-mono text-foreground">{label}</h4>
                                <p className="text-[9px] text-foreground-3 mt-0.5 leading-relaxed">{detail}</p>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Tab 2: Context / Documents */}
                      {activeHudTab === 'context' && (
                        <div className="space-y-2">
                          {mx.retrieved_context && mx.retrieved_context.length > 0 ? mx.retrieved_context.map((item: any, i: number) => (
                            <div key={i} className="p-2.5 rounded-lg border border-border bg-surface-2 text-[10px] space-y-1">
                              <div className="flex items-center justify-between">
                                <span className={`px-1.5 py-0.5 rounded-full text-[8px] font-bold uppercase ${item.type === 'memory' ? 'bg-accent/10 text-accent border border-accent/20' : 'bg-surface-3 text-foreground-2'}`}>
                                  {item.type === 'memory' ? 'Memory' : 'RAG Document'}
                                </span>
                                {item.distance != null && <span className="text-foreground-3 font-mono">dist: {Number(item.distance).toFixed(4)}</span>}
                              </div>
                              {item.filename && <p className="font-semibold text-foreground truncate">File: {item.filename}</p>}
                              <p className="text-foreground-3 leading-relaxed font-mono whitespace-pre-wrap break-all border-l-2 border-border pl-2 text-[9px]">{item.content}</p>
                            </div>
                          )) : (
                            <div className="text-center py-8 border border-dashed border-border rounded-xl text-foreground-3 text-xs">No documents or memories retrieved.</div>
                          )}
                        </div>
                      )}

                      {/* Tab 3: Search Logs */}
                      {activeHudTab === 'logs' && (
                        <div className="space-y-3">
                          {mx.search_queries && mx.search_queries.length > 0 && (
                            <div>
                              <h4 className="text-[9px] font-bold uppercase tracking-wider text-foreground-3 mb-1.5">Web Queries</h4>
                              <div className="p-2.5 rounded-lg border border-border bg-surface-2 font-mono text-[10px] space-y-1">
                                {mx.search_queries.map((q: string, i: number) => (
                                  <div key={i} className="text-foreground-2"><span className="text-foreground-3">› </span><span className="text-accent">"{q}"</span></div>
                                ))}
                              </div>
                            </div>
                          )}
                          <div>
                            <h4 className="text-[9px] font-bold uppercase tracking-wider text-foreground-3 mb-1.5">Memory Pipeline Status</h4>
                            <div className="p-2.5 rounded-lg border border-border bg-surface-2 font-mono text-[9px] text-foreground-3 space-y-1">
                              <div className="flex items-center gap-1.5 text-green-400 font-sans text-[10px]"><CheckCircle2 className="w-3 h-3" /><span className="font-semibold">Pipeline Successful</span></div>
                              <div>› Evaluated interaction for semantic facts...</div>
                              <div>› Context indexed for subsequent sessions.</div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            </>
          )}
        </aside>
      )}

      {filesModalOpen && (
        <ChatFilesModal
          onClose={() => setFilesModalOpen(false)}
          documents={chatDocuments}
          onRefresh={() => activeChatId ? fetchChatDocuments(activeChatId) : fetchDocuments()}
          token={token || ''}
          chatId={activeChatId || undefined}
          onSuccess={(msg) => addToast(msg, 'success')}
          onError={(msg) => addToast(msg, 'error')}
        />
      )}

      {/* Attached text file viewer modal */}
      <UserFileModal file={selectedUserFile} onClose={() => setSelectedUserFile(null)} />
    </div>
  );

  // ── Chat Row Renderer (ChatGPT Inspired) ───────────────────────────
  function renderChatRow(c: any, isPinned = false) {
    const active = activeChatId === c.id;
    const isMenuOpen = activeRowMenuId === c.id;
    const formattedTitle = formatChatTitle(c.title);

    return (
      <div key={c.id} className="group relative transition-all duration-150 ease-in-out">
        {renamingId === c.id ? (
          <div className="px-1 py-1">
            <input
              autoFocus
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onBlur={() => handleRenameChat(c.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRenameChat(c.id);
                if (e.key === 'Escape') setRenamingId(null);
              }}
              className="w-full bg-surface-2 border border-accent rounded-[14px] px-3 py-2 text-sm font-medium text-foreground focus:outline-none shadow-sm"
            />
          </div>
        ) : (
          <div className="relative flex items-center">
            <button
              onClick={() => { setActiveChatId(c.id); navigate(`/c/${c.id}`); }}
              className={`w-full min-h-[36px] px-3 py-1.5 rounded-[12px] flex items-center justify-between text-left transition-all duration-150 ease-in-out ${
                active
                  ? 'bg-surface-3/90 text-foreground font-semibold shadow-sm'
                  : 'text-foreground-2 hover:text-foreground hover:bg-surface-2/70'
              }`}
            >
              {/* Title with speech bubble icon for pinned items */}
              <div className="flex items-center min-w-0 flex-1 pr-2">
                {isPinned && (
                  <MessageSquare className="w-3.5 h-3.5 text-foreground-3 opacity-60 flex-shrink-0 mr-2" />
                )}
                <span className="text-[14px] font-medium leading-[18px] truncate flex-1 text-foreground">
                  {formattedTitle}
                </span>
              </div>

              {/* Relative timestamp */}
              <span className={`text-[11px] font-medium opacity-45 text-foreground-3 whitespace-nowrap flex-shrink-0 transition-opacity duration-150 ${
                isMenuOpen ? 'opacity-0' : 'group-hover:opacity-0'
              }`}>
                {formatRelativeTime(c.updated_at || c.created_at)}
              </span>
            </button>

            {/* Hover Actions: ⋯ dropdown button */}
            <div className={`absolute right-2 top-1/2 -translate-y-1/2 flex items-center z-10 transition-all duration-150 ${
              active || isMenuOpen
                ? 'opacity-100'
                : 'opacity-0 group-hover:opacity-100'
            }`}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setActiveRowMenuId(isMenuOpen ? null : c.id);
                }}
                className={`p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-all duration-150 ${
                  isMenuOpen ? 'bg-surface-3 text-foreground' : ''
                }`}
                aria-label="Conversation options"
              >
                <MoreHorizontal className="w-4 h-4" />
              </button>
            </div>

            {/* Floating Dropdown Menu */}
            {isMenuOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveRowMenuId(null);
                  }}
                />
                <div
                  onClick={(e) => e.stopPropagation()}
                  className="absolute right-2 top-full mt-1 w-48 bg-surface border border-border-2 rounded-2xl shadow-2xl p-1.5 z-50 animate-scale-in space-y-0.5"
                  style={{ animationDuration: '180ms' }}
                >
                  <button
                    onClick={() => {
                      setActiveRowMenuId(null);
                      setRenamingId(c.id);
                      setRenameValue(c.title || '');
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150 text-left"
                  >
                    <Pencil className="w-3.5 h-3.5 text-foreground-3" />
                    <span>Rename</span>
                  </button>

                  <button
                    onClick={(e) => {
                      setActiveRowMenuId(null);
                      togglePinChat(c.id, e);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150 text-left"
                  >
                    <Pin className={`w-3.5 h-3.5 ${isPinned ? 'text-accent fill-accent' : 'text-foreground-3'}`} />
                    <span>{isPinned ? 'Unpin' : 'Pin'}</span>
                  </button>

                  <button
                    onClick={() => {
                      setActiveRowMenuId(null);
                      setActiveChatId(c.id);
                      setMenuOpen(true);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150 text-left"
                  >
                    <Share2 className="w-3.5 h-3.5 text-foreground-3" />
                    <span>Share</span>
                  </button>

                  <button
                    onClick={(e) => {
                      setActiveRowMenuId(null);
                      toggleArchiveChat(c.id, e);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150 text-left"
                  >
                    <Archive className="w-3.5 h-3.5 text-foreground-3" />
                    <span>{archivedChats.includes(c.id) ? 'Unarchive' : 'Archive'}</span>
                  </button>

                  <button
                    onClick={() => {
                      setActiveRowMenuId(null);
                      setConnectedChat({ id: c.id, title: c.title || 'Untitled Chat' });
                      handleCreateChat();
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all duration-150 text-left"
                  >
                    <GitBranch className="w-3.5 h-3.5 text-foreground-3" />
                    <span>Connect to New Chat</span>
                  </button>

                  <div className="my-1 border-t border-border/60" />

                  <button
                    onClick={() => {
                      setActiveRowMenuId(null);
                      handleDeleteChat(c.id);
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 transition-all duration-150 text-left"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-rose-400" />
                    <span>Delete</span>
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    );
  }
}

interface ChatFilesModalProps {
  onClose: () => void;
  documents: any[];
  onRefresh: () => Promise<void>;
  token: string;
  chatId?: string;
  onSuccess?: (msg: string) => void;
  onError?: (msg: string) => void;
}

function ChatFilesModal({ onClose, documents, onRefresh, token, chatId, onSuccess, onError }: ChatFilesModalProps) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleUpload = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    const formData = new FormData();
    formData.append('file', file);
    if (chatId) formData.append('chat_id', chatId);

    try {
      const response = await fetch('/api/v1/documents/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || `Upload failed with status ${response.status}`);
      }

      await onRefresh();
      onSuccess?.(`"${file.name}" uploaded successfully`);
    } catch (err: any) {
      const msg = err.message || 'Failed to upload document';
      setUploadError(msg);
      onError?.(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return;
    try {
      const response = await fetch(`/api/v1/documents/${docId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) throw new Error('Failed to delete document');
      await onRefresh();
      onSuccess?.(`"${filename}" deleted`);
    } catch (err: any) {
      onError?.(err.message || 'Failed to delete document');
    }
  };

  const handleDownload = async (docId: string, filename: string) => {
    try {
      const response = await fetch(`/api/v1/documents/${docId}/download`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      if (!response.ok) throw new Error('Download failed');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(err.message || 'Failed to download document');
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleUpload(e.target.files[0]);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-surface border border-border rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-scale-in">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-surface-2/30">
          <div className="flex items-center gap-2">
            <FolderClosed className="w-5 h-5 text-accent" />
            <div>
              <h3 className="text-sm font-bold text-foreground">
                {chatId ? 'Files in This Chat' : 'Workspace Files'}
              </h3>
              <p className="text-[10px] text-foreground-3">
                {documents.length} file{documents.length !== 1 ? 's' : ''} {chatId ? 'in this chat' : 'total'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Upload box */}
        <div className="p-6 border-b border-border bg-surface-2/10">
          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelect} />
          
          {uploading ? (
            <div className="border border-dashed border-accent/30 bg-accent/5 rounded-xl p-8 flex flex-col items-center justify-center gap-3">
              <RefreshCw className="w-8 h-8 text-accent animate-spin" />
              <div className="text-center">
                <p className="text-xs font-semibold text-foreground">Uploading file...</p>
                <p className="text-[10px] text-foreground-3 mt-1">Omni is running security scans and indexing contents</p>
              </div>
            </div>
          ) : (
            <div 
              onClick={() => fileInputRef.current?.click()}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              className={`border border-dashed rounded-xl p-6 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-2 ${
                dragActive 
                  ? 'border-accent bg-accent/5 scale-[1.01]' 
                  : 'border-border/80 hover:border-accent/40 bg-surface-2/45 hover:bg-surface-2/80'
              }`}
            >
              <Upload className="w-6 h-6 text-foreground-3" />
              <div className="space-y-0.5">
                <p className="text-xs font-semibold text-foreground">Drag file here or click to browse</p>
                <p className="text-[10px] text-foreground-3">Supports PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, Images (Max 10MB)</p>
              </div>
            </div>
          )}

          {uploadError && (
            <div className="mt-3 p-2.5 rounded-lg border border-red-500/20 bg-red-500/5 text-[10px] font-medium text-red-400">
              {uploadError}
            </div>
          )}
        </div>

        {/* Scrollable File List */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {documents.length === 0 ? (
            <div className="py-12 text-center text-foreground-3 text-xs italic flex flex-col items-center gap-2">
              <Files className="w-8 h-8 text-foreground-3/55" />
              <span>No files uploaded to this workspace yet.</span>
            </div>
          ) : (
            documents.map((doc) => (
              <div key={doc.id} className="flex items-center justify-between p-3 rounded-xl border border-border bg-surface-2/50 hover:bg-surface-2 hover:border-accent/20 transition-all duration-150">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center text-accent flex-shrink-0">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-foreground truncate max-w-[280px] sm:max-w-[360px]" title={doc.filename}>
                      {doc.filename}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[9px] text-foreground-3">{formatBytes(doc.size_bytes)}</span>
                      <span className="w-1 h-1 rounded-full bg-border" />
                      <span className={`px-1.5 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wider ${
                        doc.status === 'ready' 
                          ? 'bg-green-500/10 text-green-400 border border-green-500/15'
                          : doc.status === 'failed'
                          ? 'bg-red-500/10 text-red-400 border border-red-500/15'
                          : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/15 animate-pulse'
                      }`}>
                        {doc.status}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1 flex-shrink-0">
                  <Tooltip content="Download file" side="top">
                    <button onClick={() => handleDownload(doc.id, doc.filename)} className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-all" aria-label="Download document">
                      <Download className="w-3.5 h-3.5" />
                    </button>
                  </Tooltip>
                  <Tooltip content="Delete file" side="top">
                    <button onClick={() => handleDelete(doc.id, doc.filename)} className="p-1.5 rounded-lg text-foreground-3 hover:text-red-400 hover:bg-red-500/10 transition-all" aria-label="Delete document">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </Tooltip>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// Global user file modal portal helper component
export const UserFileModal = React.memo(function UserFileModal({
  file,
  onClose,
}: {
  file: { name: string; content: string } | null;
  onClose: () => void;
}) {
  if (!file) return null;
  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-surface border border-border-2 rounded-2xl max-w-3xl w-full p-5 space-y-4 shadow-2xl">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-accent" />
            <span className="font-bold text-sm text-foreground">{file.name}</span>
            <span className="text-xs text-foreground-3">({file.content.length.toLocaleString()} chars)</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <pre className="w-full max-h-[60vh] overflow-y-auto rounded-xl bg-surface-2 p-4 text-xs font-mono text-foreground border border-border whitespace-pre-wrap break-words leading-relaxed select-text">
          {file.content}
        </pre>
        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-accent text-white text-xs font-semibold hover:opacity-90 transition-all"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
});


