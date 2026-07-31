import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Bot, User, Loader2, AlertCircle, Lock, ExternalLink, Copy, Check, Radio } from 'lucide-react';

interface SharedMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
}

interface SharedChat {
  id: string;
  title: string;
  is_live_share: boolean;
  messages: SharedMessage[];
}

function formatTime(isoStr: string): string {
  try {
    let s = isoStr.trim();
    if (!s.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(s)) {
      s = s.replace(' ', 'T');
      if (!s.includes('T')) s += 'T00:00:00Z';
      else s += 'Z';
    }
    return new Date(s).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

// Very simple inline markdown-like renderer (bold, code, newlines)
function RenderContent({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="space-y-1 text-sm leading-relaxed">
      {lines.map((line, i) => {
        if (line.startsWith('```')) {
          return null; // skip fence lines
        }
        const parts = line.split(/(\*\*[^*]+\*\*)/g);
        return (
          <p key={i} className={line === '' ? 'h-3' : ''}>
            {parts.map((part, j) =>
              part.startsWith('**') && part.endsWith('**')
                ? <strong key={j}>{part.slice(2, -2)}</strong>
                : part
            )}
          </p>
        );
      })}
    </div>
  );
}

export default function SharedChatPage() {
  const { chatId } = useParams<{ chatId: string }>();
  const navigate = useNavigate();
  const [chat, setChat] = useState<SharedChat | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchChat = async (id: string, showLoadingSpinner = false) => {
    if (showLoadingSpinner) setLoading(true);
    try {
      const res = await fetch(`/api/v1/chats/shared/${id}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data: SharedChat = await res.json();
      setChat(data);
      setLastUpdated(new Date());
      // Auto-scroll to bottom on update
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
    } catch (err: any) {
      setError(err.message || 'Failed to load shared chat.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!chatId) { setError('No chat ID provided.'); setLoading(false); return; }
    fetchChat(chatId, true);
  }, [chatId]);

  // Once we have the chat data, start polling if it's a live share
  useEffect(() => {
    if (!chat || !chat.is_live_share || !chatId) return;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => fetchChat(chatId), 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [chat?.is_live_share, chatId]);

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  /* ── Loading ── */
  if (loading) {
    return (
      <div className="min-h-screen bg-[#000000] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center">
            <Loader2 className="w-6 h-6 text-accent animate-spin" />
          </div>
          <p className="text-sm text-foreground-2">Loading shared conversation…</p>
        </div>
      </div>
    );
  }

  /* ── Error / Not found ── */
  if (error || !chat) {
    return (
      <div className="min-h-screen bg-[#000000] flex items-center justify-center p-6">
        <div className="max-w-md w-full bg-[#0B0F19] border border-border rounded-2xl p-8 flex flex-col items-center gap-6 text-center shadow-2xl">
          <div className="w-14 h-14 rounded-2xl bg-red-500/10 flex items-center justify-center">
            <Lock className="w-7 h-7 text-red-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">Snapshot Not Found</h2>
            <p className="text-sm text-foreground-3 mt-2 leading-relaxed">
              {error || 'This conversation snapshot is private, has been unshared, or the link is invalid.'}
            </p>
          </div>
          <button
            onClick={() => navigate('/login')}
            className="px-5 py-2.5 bg-accent hover:bg-accent/80 text-white rounded-xl text-sm font-semibold transition-all"
          >
            Sign in to openChat
          </button>
        </div>
      </div>
    );
  }

  const userMessages = chat.messages.filter((m) => m.role !== 'system');
  const isLive = chat.is_live_share;

  /* ── Shared chat view ── */
  return (
    <div className="min-h-screen bg-[#030712] text-foreground flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-border bg-[#030712]/80 backdrop-blur-xl">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
          {/* Brand + title */}
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-xl bg-accent flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-[10px] font-semibold text-accent uppercase tracking-widest">
                  {isLive ? 'Live Conversation' : 'Shared Conversation'}
                </p>
                {isLive && (
                  <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/25">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="text-[9px] font-bold text-emerald-400 uppercase">Live</span>
                  </span>
                )}
              </div>
              <h1 className="text-sm font-semibold text-foreground truncate">{chat.title}</h1>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {isLive && lastUpdated && (
              <span className="hidden sm:block text-[10px] text-foreground-3">
                Updated {formatTime(lastUpdated.toISOString())}
              </span>
            )}
            <button
              onClick={handleCopyLink}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-surface-2 hover:bg-surface-3 text-xs font-medium text-foreground-2 transition-all"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied' : 'Copy link'}</span>
            </button>
            <button
              onClick={() => navigate('/login')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent hover:bg-accent/80 text-xs font-semibold text-white transition-all"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Try openChat</span>
            </button>
          </div>
        </div>
      </header>

      {/* Banner — different for live vs static */}
      <div className="max-w-3xl mx-auto w-full px-4 pt-4">
        {isLive ? (
          <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-emerald-400">
            <Radio className="w-4 h-4 flex-shrink-0 animate-pulse" />
            <p className="text-xs leading-relaxed">
              This is a <strong>live conversation</strong>. New messages will automatically appear here as they are added — no need to refresh.
            </p>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-xl bg-amber-500/5 border border-amber-500/20 text-amber-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <p className="text-xs leading-relaxed">
              This is a <strong>read-only snapshot</strong> captured at share time. New messages added after sharing are not visible here.
            </p>
          </div>
        )}
      </div>

      {/* Messages */}
      <main className="flex-1 max-w-3xl mx-auto w-full px-4 py-6 space-y-6">
        {userMessages.length === 0 && (
          <div className="text-center py-16 text-foreground-3 text-sm">
            {isLive ? 'Conversation is empty — messages will appear here as they are sent.' : 'No messages in this conversation.'}
          </div>
        )}

        {userMessages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
          >
            {/* Avatar */}
            <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${
              msg.role === 'user' ? 'bg-surface-3' : 'bg-accent/10'
            }`}>
              {msg.role === 'user'
                ? <User className="w-4 h-4 text-foreground-2" />
                : <Bot className="w-4 h-4 text-accent" />
              }
            </div>

            {/* Bubble */}
            <div className={`max-w-[85%] ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
              <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-accent text-white rounded-br-sm'
                  : 'bg-surface-2 border border-border text-foreground rounded-bl-sm'
              }`}>
                {msg.role === 'assistant'
                  ? <RenderContent text={msg.content} />
                  : <p>{msg.content}</p>
                }
              </div>
              <span className="text-[10px] text-foreground-3 px-1">{formatTime(msg.created_at)}</span>
            </div>
          </div>
        ))}

        {/* Live typing indicator when polling */}
        {isLive && (
          <div className="flex gap-3 flex-row">
            <div className="w-8 h-8 rounded-xl bg-accent/10 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-accent" />
            </div>
            <div className="flex items-center gap-1.5 px-4 py-3 rounded-2xl bg-surface-2 border border-border rounded-bl-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-foreground-3 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-foreground-3 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-foreground-3 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* Footer CTA */}
      <footer className="border-t border-border bg-[#030712]/80 backdrop-blur-xl">
        <div className="max-w-3xl mx-auto px-4 py-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-xs text-foreground-3">
            Powered by <span className="text-accent font-semibold">openChat</span> — Agentic AI Workspace
          </p>
          <button
            onClick={() => navigate('/login')}
            className="flex items-center gap-2 px-5 py-2.5 bg-accent hover:bg-accent/80 text-white rounded-xl text-sm font-semibold transition-all"
          >
            <Bot className="w-4 h-4" />
            Start your own conversation
          </button>
        </div>
      </footer>
    </div>
  );
}
