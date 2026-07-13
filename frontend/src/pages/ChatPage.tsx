import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useChatStore } from '../store/chatStore';
import { useUIStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { apiRequest } from '../services/api';
import Logo from '../components/ui/Logo';
import {
  Send, Plus, Terminal, Database, User, Lock,
  Sparkles, Cpu, ChevronDown, Layers, X, CheckCircle2, Copy, Check,
  RefreshCw, ThumbsUp, ThumbsDown, ChevronLeft, ChevronRight,
  Search, MoreHorizontal, Square, ArrowDown,
  MessageSquare, Pencil, Share2, Link,
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────
//  Markdown code block component
// ─────────────────────────────────────────────────────────────
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="code-block-wrapper my-3 border border-border-2 rounded-xl overflow-hidden shadow-sm">
      <div className="code-block-header bg-surface-3 border-b border-border-2 text-foreground">
        <span className="text-foreground-2 font-semibold">{language || 'text'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-medium
                     text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
          aria-label="Copy code"
        >
          {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        style={oneDark}
        language={language || 'text'}
        PreTag="pre"
        showLineNumbers={code.split('\n').length > 4}
        wrapLongLines={false}
        customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.82rem', background: '#1e1e24' }}
        codeTagProps={{ style: { fontFamily: "'JetBrains Mono', monospace" } }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Markdown renderer
// ─────────────────────────────────────────────────────────────
function MarkdownContent({ content, isStreaming }: { content: string; isStreaming?: boolean }) {
  return (
    <div className={`prose-chat ${isStreaming ? 'streaming-cursor' : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const inline = !match;
            if (inline) {
              return <code className="text-foreground bg-surface-2 px-1.5 py-0.5 rounded text-[0.82em] border border-border-2" {...props}>{children}</code>;
            }
            return (
              <CodeBlock
                language={match[1]}
                code={String(children).replace(/\n$/, '')}
              />
            );
          },
          // Tables
          table({ children }) {
            return (
              <div className="overflow-x-auto my-3">
                <table className="min-w-full text-sm">{children}</table>
              </div>
            );
          },
          // Links open in new tab
          a({ href, children }) {
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-foreground underline underline-offset-2 hover:text-foreground-2">
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Typing indicator
// ─────────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="px-4 py-3 rounded-2xl rounded-bl-sm assistant-bubble text-sm">
      <span className="flex gap-1.5 items-center h-4">
        <span className="w-1.5 h-1.5 rounded-full bg-accent/60 animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-accent/60 animate-bounce" style={{ animationDelay: '120ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-accent/60 animate-bounce" style={{ animationDelay: '240ms' }} />
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
//  Message action button
// ─────────────────────────────────────────────────────────────
function ActionBtn({
  icon: Icon, label, onClick, active, danger, showLabel,
}: { icon: React.ElementType; label: string; onClick?: () => void; active?: boolean; danger?: boolean; showLabel?: boolean }) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`px-2 py-1 rounded-md transition-all text-[11px] flex items-center gap-1.5
        ${danger  ? 'text-foreground-3 hover:text-red-400 hover:bg-red-400/10' :
          active  ? 'text-accent bg-accent/10' :
                    'text-foreground-3 hover:text-foreground hover:bg-surface-2'}`}
    >
      <Icon className="w-3.5 h-3.5" />
      {showLabel && <span className="text-[10px] font-medium">{label}</span>}
    </button>
  );
}


// ─────────────────────────────────────────────────────────────
//  Main ChatPage
// ─────────────────────────────────────────────────────────────
export default function ChatPage() {
  const {
    chats, activeChatId, messages, activeModel, isStreaming,
    setChats, setActiveChatId, setMessages, setActiveModel, setIsStreaming,
    addChat, removeChat, updateChat, addMessage, updateLastMessageContent, updateMessage,
  } = useChatStore();

  const { developerMode, toggleDeveloperMode } = useUIStore();
  const { token, user } = useAuthStore();
  const firstName = user?.full_name?.trim().split(/\s+/)[0] || user?.email?.split('@')[0] || '';
  const greeting = firstName ? `Hi ${firstName}, How can I help you?` : 'How can I help you?';

  const [input, setInput]                         = useState('');
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [convoOpen, setConvoOpen]                 = useState(true);
  const [searchQuery, setSearchQuery]             = useState('');
  const [showSearch, setShowSearch]               = useState(false);
  const [copiedMsgId, setCopiedMsgId]             = useState<string | null>(null);
  const [likedMsgIds, setLikedMsgIds]             = useState<Set<string>>(new Set());
  const [dislikedMsgIds, setDislikedMsgIds]       = useState<Set<string>>(new Set());
  const [showScrollBtn, setShowScrollBtn]         = useState(false);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [activeHudTab, setActiveHudTab]           = useState<'flow' | 'context' | 'logs'>('flow');
  const [renamingId, setRenamingId]               = useState<string | null>(null);
  const [renameValue, setRenameValue]             = useState('');
  const [openMenuId, setOpenMenuId]               = useState<string | null>(null);
  // Edit state
  const [editingMsgId, setEditingMsgId]           = useState<string | null>(null);
  const [editValue, setEditValue]                 = useState('');
  const editTextareaRef                           = useRef<HTMLTextAreaElement>(null);
  // Share state
  const [shareOpen, setShareOpen]                 = useState(false);
  const [copiedShareLink, setCopiedShareLink]     = useState(false);


  const messagesEndRef   = useRef<HTMLDivElement>(null);
  const chatScrollRef    = useRef<HTMLDivElement>(null);
  const textareaRef      = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const models = [
    { id: 'gemini-1.5-flash',  name: 'Gemini 1.5 Flash', provider: 'Google', icon: Cpu,      desc: 'Fast multimodal model' },
    { id: 'gemini-1.5-pro',    name: 'Gemini 1.5 Pro',   provider: 'Google', icon: Sparkles, desc: 'Advanced reasoning' },
    { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B',   provider: 'Groq',   icon: Terminal,  desc: 'Ultra-fast open source' },
    { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B', provider: 'Groq',   icon: Layers,   desc: 'Capable open source' },
  ];
  const currentModel = models.find((m) => m.id === activeModel) || models[0];
  const activeChat = chats.find((c) => c.id === activeChatId);

  // ── Fetch chats
  useEffect(() => {
    apiRequest('/chats')
      .then((data) => setChats(data))
      .catch((err) => console.error('Failed to fetch chats:', err));
  }, [setChats]);

  // ── Fetch messages
  useEffect(() => {
    if (activeChatId) {
      apiRequest(`/chats/${activeChatId}`)
        .then((data) => setMessages(data))
        .catch((err) => console.error('Failed to fetch messages:', err));
    } else {
      setMessages([]);
    }
  }, [activeChatId, setMessages]);

  // ── Reset share panel when switching chats (per-chat share state)
  useEffect(() => {
    setShareOpen(false);
    setCopiedShareLink(false);
  }, [activeChatId]);

  // ── Auto-scroll during streaming
  useEffect(() => {
    if (isStreaming) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isStreaming]);

  // ── Track last assistant message for HUD
  const assistantMessages = messages.filter((m) => m.role === 'assistant');
  const lastAssistantMsg  = assistantMessages[assistantMessages.length - 1];
  useEffect(() => {
    if (lastAssistantMsg && (isStreaming || !selectedMessageId)) {
      setSelectedMessageId(lastAssistantMsg.id);
    }
    if (!lastAssistantMsg) setSelectedMessageId(null);
  }, [messages, isStreaming, lastAssistantMsg]);

  // ── Scroll-to-bottom detection
  const handleScroll = () => {
    const el = chatScrollRef.current;
    if (!el) return;
    setShowScrollBtn(el.scrollHeight - el.scrollTop - el.clientHeight > 120);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // ── Auto resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
  }, [input]);

  // ── Create chat
  const handleCreateChat = async () => {
    try {
      const newChat = await apiRequest('/chats', { method: 'POST', json: { title: 'New Chat' } });
      addChat(newChat);
      setActiveChatId(newChat.id);
    } catch (err) {
      console.error('Failed to create chat:', err);
    }
  };

  // ── Delete chat
  const handleDeleteChat = async (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    try {
      await apiRequest(`/chats/${id}`, { method: 'DELETE' });
      removeChat(id);
    } catch (err) {
      console.error('Failed to delete chat:', err);
    }
  };

  // ── Rename chat
  const handleRenameChat = async (id: string) => {
    if (!renameValue.trim()) { setRenamingId(null); return; }
    try {
      await apiRequest(`/chats/${id}`, { method: 'PATCH', json: { title: renameValue.trim() } });
      setChats(chats.map((c) => c.id === id ? { ...c, title: renameValue.trim() } : c));
    } catch {
      // Optimistic fallback
      setChats(chats.map((c) => c.id === id ? { ...c, title: renameValue.trim() } : c));
    } finally {
      setRenamingId(null);
    }
  };

  // ── Stop streaming
  const handleStopGeneration = () => {
    abortControllerRef.current?.abort();
    setIsStreaming(false);
  };

  // ── Send message
  const handleSendMessage = async (e: React.FormEvent | null, promptOverride?: string) => {
    e?.preventDefault();
    const text = (promptOverride ?? input).trim();
    if (!text || isStreaming) return;

    let chatId = activeChatId;
    if (!chatId) {
      try {
        const newChat = await apiRequest('/chats', {
          method: 'POST',
          json: { title: text.substring(0, 40) },
        });
        addChat(newChat);
        chatId = newChat.id;
        setActiveChatId(chatId);
      } catch (err) { console.error('Auto-create chat failed:', err); return; }
    }

    setInput('');
    const userMsg = {
      id: crypto.randomUUID(),
      chat_id: chatId!,
      parent_id: messages.length > 0 ? messages[messages.length - 1].id : null,
      role: 'user' as const,
      content: text,
      tool_calls: null,
      developer_metrics: null,
      created_at: new Date().toISOString(),
    };
    addMessage(userMsg);

    const asstId = crypto.randomUUID();
    addMessage({
      id: asstId,
      chat_id: chatId!,
      parent_id: userMsg.id,
      role: 'assistant' as const,
      content: '',
      tool_calls: null,
      developer_metrics: null,
      created_at: new Date().toISOString(),
    });
    setIsStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let asstText = '';

    try {
      const res = await fetch(`/api/v1/chats/${chatId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: text, model: activeModel, parent_message_id: userMsg.parent_id }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      if (!reader) throw new Error('No reader');

      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines  = buffer.split('\n');
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
              updateLastMessageContent(asstText);
            } else if (parsed.event === 'metrics') {
              updateMessage(asstId, { developer_metrics: parsed.metrics });
            } else if (parsed.event === 'error') {
              asstText += `\n\n*[Error: ${parsed.detail || 'Failed to generate response'}]*`;
              updateLastMessageContent(asstText);
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        updateLastMessageContent(asstText + '\n\n*[Response interrupted or connection lost.]*');
      }
    } finally {
      setIsStreaming(false);
    }
  };

  // ── Copy message
  const handleCopyMessage = (id: string, content: string) => {
    navigator.clipboard.writeText(content).then(() => {
      setCopiedMsgId(id);
      setTimeout(() => setCopiedMsgId(null), 2000);
    });
  };

  // ── Edit user message: open inline editor
  const handleStartEdit = (id: string, content: string) => {
    setEditingMsgId(id);
    setEditValue(content);
    setTimeout(() => {
      editTextareaRef.current?.focus();
      editTextareaRef.current?.select();
    }, 50);
  };

  // ── Submit edited message: truncate history after this msg, re-send
  const handleSubmitEdit = async (msgId: string) => {
    const newText = editValue.trim();
    if (!newText || !activeChatId) { setEditingMsgId(null); return; }

    // Find the index of the edited message
    const editIdx = messages.findIndex((m) => m.id === msgId);
    if (editIdx === -1) { setEditingMsgId(null); return; }

    // Keep all messages up to (but not including) the edited one
    const trimmedMessages = messages.slice(0, editIdx);
    setMessages(trimmedMessages);
    setEditingMsgId(null);

    // Re-send as a new message with the updated text
    await handleSendMessage(null, newText);
  };

  // ── Cancel edit
  const handleCancelEdit = () => {
    setEditingMsgId(null);
    setEditValue('');
  };

  // ── Retry: find preceding user message and re-send it
  const handleRetry = async (assistantMsgIdx: number) => {
    if (isStreaming) return;
    // Walk backwards from the assistant message to find the user message
    let userMsg = null;
    for (let i = assistantMsgIdx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { userMsg = messages[i]; break; }
    }
    if (!userMsg) return;

    // Trim messages to before the user message, then re-send
    const trimmedMessages = messages.slice(0, messages.indexOf(userMsg));
    setMessages(trimmedMessages);
    await handleSendMessage(null, userMsg.content);
  };

  // ── Like / Dislike
  const handleLike = (id: string) => {
    setLikedMsgIds((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
    setDislikedMsgIds((prev) => { const n = new Set(prev); n.delete(id); return n; });
  };
  const handleDislike = (id: string) => {
    setDislikedMsgIds((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
    setLikedMsgIds((prev) => { const n = new Set(prev); n.delete(id); return n; });
  };

  // ── Share chat
  const handleToggleShare = async (chatId: string, isShared: boolean) => {
    try {
      const updated = await apiRequest(`/chats/${chatId}/share`, {
        method: 'POST',
        json: { is_shared: isShared }
      });
      updateChat(updated);
    } catch (err) {
      console.error('Failed to toggle share status:', err);
    }
  };

  // ── Keyboard
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  // ── Filtered chats
  const filteredChats = chats.filter((c) =>
    !searchQuery || (c.title || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  // ─────────────────────────────────────────────────────────────
  //  RENDER
  // ─────────────────────────────────────────────────────────────
  return (
    <div className="h-full w-full flex overflow-hidden" role="main">

      {/* ══════════ CONVERSATION SIDEBAR ══════════ */}
      <aside
        className="flex flex-col border-r border-border bg-surface flex-shrink-0 sidebar-transition hidden lg:flex"
        style={{ width: convoOpen ? '240px' : '52px' }}
        aria-label="Conversations"
      >
        {/* Header */}
        <div className="h-[var(--header-height)] border-b border-border flex items-center flex-shrink-0 px-2 gap-1.5 bg-surface light-dark">
          {convoOpen ? (
            <>
              <span className="text-[11px] font-semibold text-foreground-3 uppercase tracking-wider flex-1 px-1">
                Conversations
              </span>
              <button
                onClick={() => setShowSearch((v) => !v)}
                className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
                title="Search chats"
              >
                <Search className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={handleCreateChat}
                className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
                title="New Chat"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setConvoOpen(false)}
                className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
                title="Collapse"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
            </>
          ) : (
            <div className="flex items-center justify-center w-full">
              <button
                onClick={() => setConvoOpen(true)}
                className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
                title="Expand conversations"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>

        {/* Search */}
        {convoOpen && showSearch && (
          <div className="px-2 pt-2 pb-1 border-b border-border flex-shrink-0">
            <div className="relative">
              <Search className="absolute left-2.5 top-2 w-3 h-3 text-foreground-3" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search conversations..."
                className="w-full bg-surface-2 border border-border rounded-lg pl-7 pr-3 py-1.5 text-xs text-foreground placeholder:text-foreground-3 focus:outline-none focus:border-accent transition-colors"
                autoFocus
              />
            </div>
          </div>
        )}

        {/* Chat list */}
        {convoOpen && (
          <div className="flex-1 overflow-y-auto py-2 px-1.5 space-y-0.5">
            {filteredChats.map((c) => (
              <div key={c.id} className="group relative">
                {renamingId === c.id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => handleRenameChat(c.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameChat(c.id);
                      if (e.key === 'Escape') setRenamingId(null);
                    }}
                    className="w-full bg-surface-2 border border-accent rounded-lg px-2 py-1.5 text-xs text-foreground focus:outline-none"
                  />
                ) : (
                  <button
                    onClick={() => setActiveChatId(c.id)}
                    className={`w-full text-left px-2.5 py-2 rounded-lg text-xs font-medium flex items-center gap-2 transition-all
                      ${activeChatId === c.id
                        ? 'bg-accent/10 text-foreground border border-accent/20'
                        : 'text-foreground-2 hover:text-foreground hover:bg-surface-2'}`}
                  >
                    <MessageSquare className="w-3 h-3 flex-shrink-0 text-foreground-3" />
                    <span className="truncate flex-1">{c.title || 'New Chat'}</span>
                  </button>
                )}

                {/* Context menu button */}
                <button
                  onClick={(e) => { e.stopPropagation(); setOpenMenuId(openMenuId === c.id ? null : c.id); }}
                  className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded opacity-0 group-hover:opacity-100
                             text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-all"
                >
                  <MoreHorizontal className="w-3 h-3" />
                </button>

                {/* Context dropdown */}
                {openMenuId === c.id && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpenMenuId(null)} />
                    <div className="absolute right-0 top-full mt-0.5 w-36 glass-heavy rounded-lg shadow-xl p-1 z-50 animate-scale-in">
                      <button
                        onClick={() => { setRenamingId(c.id); setRenameValue(c.title || ''); setOpenMenuId(null); }}
                        className="w-full text-left px-2.5 py-1.5 text-xs rounded-md text-foreground-2 hover:bg-surface-2 hover:text-foreground transition-all"
                      >
                        Rename
                      </button>
                      <button
                        onClick={() => { handleDeleteChat(c.id); setOpenMenuId(null); }}
                        className="w-full text-left px-2.5 py-1.5 text-xs rounded-md text-red-400 hover:bg-red-500/10 transition-all"
                      >
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}

            {filteredChats.length === 0 && (
              <div className="py-10 text-center text-foreground-3 text-xs">
                {searchQuery ? 'No results found' : 'No conversations yet'}
              </div>
            )}
          </div>
        )}

        {/* Collapsed sidebar actions */}
        {!convoOpen && (
          <div className="flex-1 flex flex-col items-center py-3 px-1.5 gap-3 bg-transparent">
            {/* New Chat button */}
            <button
              onClick={handleCreateChat}
              data-tooltip="New Chat"
              aria-label="New Chat"
              className="w-8 h-8 rounded-lg flex items-center justify-center text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all"
            >
              <Plus className="w-4 h-4" />
            </button>

            {/* List of chat icons */}
            <div className="flex-1 w-full overflow-y-auto overflow-x-hidden space-y-1 flex flex-col items-center">
              {chats.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setActiveChatId(c.id)}
                  data-tooltip={c.title || 'New Chat'}
                  aria-label={c.title || 'New Chat'}
                  className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all
                    ${activeChatId === c.id
                      ? 'bg-accent/10 text-accent border border-accent/20'
                      : 'text-foreground-2 hover:text-foreground hover:bg-surface-2'}`}
                >
                  <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
                </button>
              ))}
            </div>

            {/* Total chat count badge at the bottom */}
            {chats.length > 0 && (
              <span className="text-[10px] font-bold text-foreground-3 mb-2">{chats.length}</span>
            )}
          </div>
        )}
      </aside>

      {/* ══════════ MAIN CHAT ══════════ */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">

        {/* Toolbar */}
        <header className="h-[var(--header-height)] px-4 border-b border-border flex items-center justify-between bg-surface flex-shrink-0 z-10 light-dark">
          <div className="flex items-center gap-2 min-w-0">
            {/* Mobile: open convo panel */}
            <button onClick={() => setConvoOpen((v) => !v)} className="lg:hidden p-1.5 text-foreground-3 hover:text-foreground">
              <MessageSquare className="w-4 h-4" />
            </button>
            <span className="font-medium text-sm truncate text-foreground">
              {activeChatId ? chats.find((c) => c.id === activeChatId)?.title || 'Chat' : 'New Chat'}
            </span>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Dev HUD */}
            <button
              onClick={toggleDeveloperMode}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-all
                ${developerMode
                  ? 'border-accent/40 bg-accent/10 text-accent'
                  : 'border-border bg-surface-2 text-foreground-2 hover:text-foreground hover:bg-surface-3'}`}
              title="Toggle Developer HUD"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Dev HUD</span>
            </button>

            {/* Share button */}
            {activeChat && (
              <div className="relative">
                <button
                  onClick={() => setShareOpen((v) => !v)}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-all
                    ${activeChat.is_shared
                      ? 'border-green-500/40 bg-green-500/10 text-green-400'
                      : 'border-border bg-surface-2 text-foreground-2 hover:text-foreground hover:bg-surface-3'}`}
                  title="Share chat"
                >
                  <Share2 className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Share</span>
                </button>

                {shareOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShareOpen(false)} />
                    <div className="absolute right-0 top-full mt-1.5 w-80 bg-surface border border-border-2 rounded-2xl shadow-2xl p-4 z-50 animate-scale-in space-y-4">

                      {/* Header */}
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <Share2 className="w-3.5 h-3.5 text-foreground" />
                          <h4 className="text-xs font-semibold text-foreground">Share conversation</h4>
                        </div>
                        <p className="text-[10px] text-foreground-3 leading-relaxed">
                          Sharing creates a <strong className="text-foreground-2">static snapshot</strong> of this conversation at this moment. New messages will not be visible to viewers.
                        </p>
                      </div>

                      {/* Privacy notice */}
                      <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-amber-500/5 border border-amber-500/15">
                        <Lock className="w-3 h-3 text-amber-400 mt-0.5 flex-shrink-0" />
                        <p className="text-[10px] text-amber-400/90 leading-relaxed">
                          Only the messages visible right now are included. Your future replies stay private.
                        </p>
                      </div>

                      {/* Toggle */}
                      <div className="flex items-center justify-between py-1.5 px-3 rounded-xl bg-surface-2 border border-border">
                        <span className="text-[10px] font-medium text-foreground-2">Enable public link</span>
                        <button
                          type="button"
                          onClick={() => handleToggleShare(activeChat.id, !activeChat.is_shared)}
                          className={`w-8 h-4 rounded-full transition-colors relative flex items-center ${activeChat.is_shared ? 'bg-accent' : 'bg-surface-3'}`}
                        >
                          <span className={`w-3.5 h-3.5 rounded-full bg-white transition-transform ${activeChat.is_shared ? 'translate-x-4' : 'translate-x-0.5'}`} />
                        </button>
                      </div>

                      {/* Shareable link — only shown when shared and share_id is available */}
                      {activeChat.is_shared && activeChat.share_id && (
                        <div className="space-y-1.5 animate-slide-up">
                          <div className="flex items-center gap-1.5">
                            <label className="text-[9px] font-semibold text-foreground-3 uppercase">Shareable Link</label>
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-green-500/10 text-green-400 font-semibold border border-green-500/20">Snapshot</span>
                          </div>
                          <div className="flex gap-1.5">
                            <input
                              readOnly
                              value={`${window.location.origin}/share/${activeChat.share_id}`}
                              className="flex-1 bg-surface-2 border border-border rounded-lg px-2.5 py-1 text-[10px] font-mono text-foreground focus:outline-none"
                            />
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(`${window.location.origin}/share/${activeChat.share_id}`);
                                setCopiedShareLink(true);
                                setTimeout(() => setCopiedShareLink(false), 2500);
                              }}
                              className="px-2 rounded-lg bg-accent text-white text-[10px] font-semibold hover:opacity-90 transition-all flex items-center justify-center gap-1"
                            >
                              {copiedShareLink ? <Check className="w-3 h-3" /> : <Link className="w-3 h-3" />}
                              <span>{copiedShareLink ? 'Copied' : 'Copy'}</span>
                            </button>
                          </div>
                          <p className="text-[9px] text-foreground-3 leading-relaxed">
                            Turning sharing off will invalidate this link permanently.
                          </p>
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Model picker */}
            <div className="relative">
              <button
                onClick={() => setModelDropdownOpen((v) => !v)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border bg-surface-2 hover:bg-surface-3 text-xs font-semibold text-foreground transition-all"
              >
                <currentModel.icon className="w-3.5 h-3.5 text-accent" />
                <span className="hidden sm:inline">{currentModel.name}</span>
                <ChevronDown className="w-3 h-3 text-foreground-3" />
              </button>

              {modelDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setModelDropdownOpen(false)} />
                  <div className="absolute right-0 top-full mt-1.5 w-64 glass-heavy rounded-xl shadow-2xl p-1.5 z-50 space-y-0.5 animate-scale-in">
                    {models.map((m) => {
                      const Icon = m.icon;
                      return (
                        <button
                          key={m.id}
                          onClick={() => { setActiveModel(m.id); setModelDropdownOpen(false); }}
                          className={`w-full flex items-start gap-2.5 px-3 py-2.5 rounded-lg text-xs transition-all
                            ${activeModel === m.id ? 'bg-accent/15 text-foreground border border-accent/20' : 'text-foreground-2 hover:text-foreground hover:bg-surface-2'}`}
                        >
                          <Icon className="w-3.5 h-3.5 mt-0.5 text-accent flex-shrink-0" />
                          <div className="text-left">
                            <div className="font-semibold">{m.name}</div>
                            <div className="text-[10px] text-foreground-3 mt-0.5">{m.provider} · {m.desc}</div>
                          </div>
                          {activeModel === m.id && <CheckCircle2 className="w-3.5 h-3.5 text-accent ml-auto mt-0.5" />}
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          </div>
        </header>

        {/* Messages */}
        <div
          ref={chatScrollRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-4 py-6 space-y-5"
          style={{ scrollBehavior: 'smooth' }}
        >
          {/* Welcome / Empty state */}
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-xl mx-auto py-12 space-y-6 animate-fade-in">
              <div className="w-16 h-16 rounded-2xl bg-accent/10 border border-accent/20 flex items-center justify-center mx-auto shadow-lg shadow-accent/10">
                <Logo size={36} collapsed />
              </div>
              <h2 className="text-2xl md:text-3xl font-semibold text-foreground tracking-tight">
                {greeting}
              </h2>
            </div>
          )}

          {/* Message list */}
          {messages.map((m, idx) => {
            if (m.role === 'system' || m.role === 'tool') return null;
            const isUser          = m.role === 'user';
            const isLastAsst      = !isUser && idx === messages.length - 1;
            const isStreamingThis = isStreaming && isLastAsst && m.content === '';
            const isEditing       = editingMsgId === m.id;

            return (
              <div
                key={m.id}
                className={`flex gap-3 animate-slide-up group/msg ${isUser ? 'justify-end' : 'justify-start'}`}
                style={{ animationDelay: `${Math.min(idx * 20, 200)}ms` }}
              >
                {/* Bot avatar */}
                {!isUser && (
                  <div className="w-7 h-7 rounded-full bg-accent/15 border border-accent/30 flex items-center justify-center flex-shrink-0 mt-1">
                    <Logo size={16} collapsed />
                  </div>
                )}

                <div className={`max-w-[82%] flex flex-col gap-1.5 ${isUser ? 'items-end' : 'items-start'}`}>

                  {/* ── USER MESSAGE ── */}
                  {isUser && (
                    isEditing ? (
                      /* ── Inline Edit Mode ── */
                      <div className="w-full min-w-[280px] space-y-2">
                        <textarea
                          ref={editTextareaRef}
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmitEdit(m.id); }
                            if (e.key === 'Escape') handleCancelEdit();
                          }}
                          rows={Math.max(2, editValue.split('\n').length)}
                          className="w-full rounded-xl px-3.5 py-2.5 text-sm text-foreground bg-surface border border-accent/40 focus:outline-none focus:ring-1 focus:ring-accent resize-none leading-relaxed"
                          style={{ minHeight: '72px', maxHeight: '240px' }}
                        />
                        <div className="flex items-center gap-1.5 justify-end">
                          <button
                            onClick={handleCancelEdit}
                            className="px-3 py-1.5 rounded-lg text-[11px] font-medium text-foreground-3 hover:text-foreground bg-surface-2 hover:bg-surface-3 border border-border transition-all"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleSubmitEdit(m.id)}
                            disabled={!editValue.trim()}
                            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold text-white bg-accent hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1.5"
                          >
                            <Send className="w-3 h-3" />
                            Send Edit
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* ── Normal user bubble ── */
                      <div className="user-bubble rounded-2xl rounded-br-sm px-4 py-3 text-sm">
                        <p className="whitespace-pre-wrap break-words leading-relaxed text-white">{m.content}</p>
                      </div>
                    )
                  )}

                  {/* ── ASSISTANT MESSAGE ── */}
                  {!isUser && (
                    isStreamingThis ? (
                      <TypingIndicator />
                    ) : (
                      <div className="assistant-bubble text-foreground rounded-2xl rounded-bl-sm px-4 py-3 text-sm">
                        <MarkdownContent
                          content={m.content}
                          isStreaming={isStreaming && isLastAsst && m.content !== ''}
                        />
                      </div>
                    )
                  )}

                  {/* ── USER action row (copy + edit) ── */}
                  {isUser && !isEditing && (
                    <div
                      className="flex items-center gap-0.5 opacity-0 group-hover/msg:opacity-100 transition-all duration-150 mt-0.5"
                    >
                      <ActionBtn
                        icon={copiedMsgId === m.id ? Check : Copy}
                        label={copiedMsgId === m.id ? 'Copied!' : 'Copy'}
                        showLabel
                        onClick={() => handleCopyMessage(m.id, m.content)}
                        active={copiedMsgId === m.id}
                      />
                      <ActionBtn
                        icon={Pencil}
                        label="Edit"
                        showLabel
                        onClick={() => handleStartEdit(m.id, m.content)}
                      />
                    </div>
                  )}

                  {/* ── ASSISTANT action row (copy + like + dislike + retry) ── */}
                  {!isUser && m.content && !isStreamingThis && (
                    <div
                      className="flex items-center gap-0.5 opacity-0 group-hover/msg:opacity-100 transition-all duration-150 mt-0.5"
                    >
                      <ActionBtn
                        icon={copiedMsgId === m.id ? Check : Copy}
                        label={copiedMsgId === m.id ? 'Copied!' : 'Copy'}
                        showLabel
                        onClick={() => handleCopyMessage(m.id, m.content)}
                        active={copiedMsgId === m.id}
                      />
                      <div className="w-px h-3.5 bg-border mx-0.5" />
                      <ActionBtn icon={ThumbsUp}   label="Like"    onClick={() => handleLike(m.id)}    active={likedMsgIds.has(m.id)} />
                      <ActionBtn icon={ThumbsDown} label="Dislike" onClick={() => handleDislike(m.id)} active={dislikedMsgIds.has(m.id)} />
                      <div className="w-px h-3.5 bg-border mx-0.5" />
                      <ActionBtn
                        icon={RefreshCw}
                        label="Retry"
                        showLabel
                        onClick={() => handleRetry(idx)}
                      />
                    </div>
                  )}
                </div>

                {/* User avatar */}
                {isUser && !isEditing && (
                  <div className="w-7 h-7 rounded-full bg-surface-2 border border-border-2 flex items-center justify-center flex-shrink-0 mt-1">
                    <User className="w-3.5 h-3.5 text-foreground-2" />
                  </div>
                )}
              </div>
            );
          })}

          <div ref={messagesEndRef} />
        </div>

        {/* Scroll to bottom button */}
        {showScrollBtn && (
          <button
            onClick={scrollToBottom}
            className="scroll-btn p-2 rounded-full bg-surface border border-border shadow-lg text-foreground-2 hover:text-foreground hover:bg-surface-2 transition-all animate-fade-in"
            aria-label="Scroll to bottom"
          >
            <ArrowDown className="w-4 h-4" />
          </button>
        )}

        {/* Input bar */}
        <footer className="px-4 py-4 flex-shrink-0">
          <form onSubmit={handleSendMessage} className="max-w-chat mx-auto">
            <div className="flex items-end gap-2 rounded-2xl border border-border-2 bg-surface-2 focus-within:border-accent/60 focus-within:bg-surface-3 transition-all duration-150 px-3 py-2 shadow-lg shadow-black/20">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message Omni..."
                rows={1}
                className="flex-1 bg-transparent resize-none py-1 px-1 text-sm text-foreground placeholder:text-foreground-3 focus:outline-none leading-relaxed"
                style={{ maxHeight: '180px', minHeight: '24px' }}
                aria-label="Message input"
              />
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {isStreaming ? (
                  <button
                    type="button"
                    onClick={handleStopGeneration}
                    className="p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-all"
                    title="Stop generation"
                  >
                    <Square className="w-4 h-4" />
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!input.trim()}
                    className="p-2 rounded-lg bg-accent text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
                    title="Send (Enter)"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
            <p className="text-center text-[10px] text-foreground-3/60 mt-2">
              Enter to send · Shift+Enter for newline · Omni may make mistakes
            </p>
          </form>
        </footer>
      </div>

      {/* ══════════ DEV HUD PANEL ══════════ */}
      {developerMode && (
        <aside className="w-[380px] border-l border-border bg-surface flex flex-col flex-shrink-0 animate-slide-right overflow-hidden">
          {/* HUD Header */}
          <div className="h-[var(--header-height)] px-4 border-b border-border flex items-center justify-between flex-shrink-0 bg-surface-2">
            <div className="flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5 text-accent" />
              <span className="text-xs font-semibold text-foreground">Execution Telemetry</span>
            </div>
            <button onClick={toggleDeveloperMode} className="p-1 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-3 transition-all">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {(() => {
              const msg = messages.find((m) => m.id === selectedMessageId);
              if (!msg) return (
                <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-2">
                  <Database className="w-8 h-8 text-foreground-3/40" />
                  <p className="text-xs text-foreground-3">Select an assistant message to inspect telemetry</p>
                </div>
              );

              const mx = msg.developer_metrics;
              if (!mx) return (
                <div className="text-center py-6 text-xs text-foreground-3">No telemetry for this message.</div>
              );

              const steps  = mx.steps || ['retrieve_context', 'generate_response'];
              const hasTool = msg.tool_calls && msg.tool_calls.length > 0;

              return (
                <div className="space-y-4">
                  {/* Metrics grid */}
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { label: 'Model',      val: mx.model_used, color: '' },
                      { label: 'Latency',    val: mx.latency_ms >= 1000 ? `${(mx.latency_ms/1000).toFixed(2)}s` : `${mx.latency_ms}ms`, color: '' },
                      { label: 'Tokens In',  val: mx.tokens_input.toLocaleString(), color: '' },
                      { label: 'Tokens Out', val: mx.tokens_output.toLocaleString(), color: '' },
                      { label: 'Est. Cost',  val: `$${(mx.cost_estimate ?? 0).toFixed(6)}`, color: 'text-green-400' },
                      { label: 'Mem Hits',   val: String(mx.memory_hits), color: '' },
                    ].map(({ label, val, color }) => (
                      <div key={label} className="p-2.5 rounded-xl border border-border bg-surface-2 space-y-1">
                        <span className="text-[9px] font-semibold uppercase tracking-wider text-foreground-3">{label}</span>
                        <p className={`text-xs font-bold truncate ${color || 'text-foreground'}`}>{val}</p>
                      </div>
                    ))}
                  </div>

                  {/* HUD tabs */}
                  <div className="flex border-b border-border">
                    {(['flow', 'context', 'logs'] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveHudTab(tab)}
                        className={`flex-1 pb-1.5 text-[9px] font-bold uppercase tracking-wider transition-all
                          ${activeHudTab === tab
                            ? 'border-b-2 border-accent text-accent'
                            : 'text-foreground-3 hover:text-foreground border-b-2 border-transparent'}`}
                      >
                        {tab === 'flow' ? 'Flow' : tab === 'context' ? 'Context' : 'Logs'}
                      </button>
                    ))}
                  </div>

                  {/* Tab content */}
                  {activeHudTab === 'flow' && (
                    <div className="pl-5 space-y-5 relative before:absolute before:left-2 before:top-1 before:bottom-1 before:w-px before:bg-border">
                      {[
                        { key: 'retrieve_context',  label: 'retrieve_context',  icon: Database, detail: `Hits: ${mx.memory_hits} memory / ${mx.chunks_used ?? 0} chunks` },
                        { key: 'generate_response', label: 'generate_response', icon: Cpu,      detail: 'LLM processed context & generated reply' },
                        { key: 'execute_tools',     label: 'execute_tools',     icon: Terminal, detail: hasTool ? `${msg.tool_calls!.length} tool(s) called` : 'Skipped' },
                        { key: 'synthesize',        label: 'synthesize',        icon: Sparkles, detail: 'Final synthesis & streaming output' },
                      ].map(({ key, label, icon: Icon, detail }) => {
                        const active = steps.includes(key) || (key === 'execute_tools' && hasTool);
                        return (
                          <div key={key} className="relative">
                            <div className={`absolute -left-5 w-4 h-4 rounded-full border flex items-center justify-center
                              ${active ? 'border-accent bg-accent/10 text-accent' : 'border-border bg-surface text-foreground-3 opacity-50'}`}>
                              <Icon className="w-2.5 h-2.5" />
                            </div>
                            <h4 className="text-[10px] font-semibold font-mono text-foreground">{label}</h4>
                            <p className="text-[10px] text-foreground-3 mt-0.5 leading-relaxed">{detail}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {activeHudTab === 'context' && (
                    <div className="space-y-2">
                      {mx.retrieved_context && mx.retrieved_context.length > 0 ? mx.retrieved_context.map((item, i) => (
                        <div key={i} className="p-2.5 rounded-lg border border-border bg-surface-2 text-[10px] space-y-1">
                          <div className="flex items-center justify-between">
                            <span className={`px-1.5 py-0.5 rounded-full text-[8px] font-bold uppercase
                              ${item.type === 'memory' ? 'bg-accent/10 text-foreground border border-accent/20' : 'bg-surface-3 text-foreground-2 border border-border-2'}`}>
                              {item.type === 'memory' ? `Memory: ${item.category || 'fact'}` : 'RAG Chunk'}
                            </span>
                            {item.distance !== undefined && (
                              <span className="text-foreground-3 font-mono">dist: {item.distance.toFixed(4)}</span>
                            )}
                          </div>
                          {item.filename && <p className="font-semibold text-foreground truncate">File: {item.filename}</p>}
                          <p className="text-foreground-3 leading-relaxed font-mono whitespace-pre-wrap break-all border-l-2 border-border pl-2 text-[9px]">{item.content}</p>
                        </div>
                      )) : (
                        <div className="text-center py-6 border border-dashed border-border rounded-xl text-foreground-3 text-xs">
                          No retrieval context injected for this response.
                        </div>
                      )}
                    </div>
                  )}

                  {activeHudTab === 'logs' && (
                    <div className="space-y-3">
                      {mx.search_queries && mx.search_queries.length > 0 && (
                        <div>
                          <h4 className="text-[9px] font-bold uppercase tracking-wider text-foreground-3 mb-1.5">Web Search Queries</h4>
                          <div className="p-2.5 rounded-lg border border-border bg-surface-2 font-mono text-[10px] space-y-1">
                            {mx.search_queries.map((q, i) => (
                              <div key={i} className="text-foreground-2">
                                <span className="text-foreground-3">› </span>
                                <span className="text-accent">"{q}"</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div>
                        <h4 className="text-[9px] font-bold uppercase tracking-wider text-foreground-3 mb-1.5">Memory Pipeline</h4>
                        <div className="p-2.5 rounded-lg border border-border bg-surface-2 font-mono text-[9px] text-foreground-3 space-y-1.5">
                          <div className="flex items-center gap-1.5 text-green-400 font-sans text-[10px]">
                            <CheckCircle2 className="w-3 h-3" />
                            <span className="font-semibold">Pipeline Success</span>
                          </div>
                          <div>› Scanning interaction for facts/preferences...</div>
                          <div>› Deduplication registry checked.</div>
                          <div>› Context indexed for subsequent sessions.</div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </aside>
      )}
    </div>
  );
}
