import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, X, MessageSquare, Clock } from 'lucide-react';

interface Chat {
  id: string;
  title: string;
  updated_at?: string;
  created_at?: string;
}

interface GlobalSearchProps {
  open: boolean;
  onClose: () => void;
  chats: Chat[];
  onSelectChat: (id: string) => void;
}

const MAX_RECENT = 5;
const RECENT_KEY = 'omni_recent_searches';

function highlight(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase()
      ? <mark key={i} className="bg-accent/25 text-accent rounded px-0.5">{part}</mark>
      : part
  );
}

export default function GlobalSearch({ open, onClose, chats, onSelectChat }: GlobalSearchProps) {
  const [query, setQuery]             = useState('');
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [recentSearches, setRecent]   = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; }
  });

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIdx(0);
      setTimeout(() => inputRef.current?.focus(), 60);
    }
  }, [open]);

  const saveRecent = useCallback((q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    const next = [trimmed, ...recentSearches.filter((r) => r !== trimmed)].slice(0, MAX_RECENT);
    setRecent(next);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  }, [recentSearches]);

  const filtered = query.trim()
    ? chats.filter((c) => (c.title || '').toLowerCase().includes(query.toLowerCase()))
    : [];

  const results = filtered.slice(0, 8);

  const handleSelect = useCallback((id: string, title: string) => {
    saveRecent(title);
    onSelectChat(id);
    onClose();
  }, [saveRecent, onSelectChat, onClose]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      if (results[selectedIdx]) {
        handleSelect(results[selectedIdx].id, results[selectedIdx].title);
      }
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="search-overlay-bg" onClick={onClose} aria-hidden="true" />

      {/* Panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search chats"
        className="search-panel"
      >
        <div className="glass-heavy rounded-2xl shadow-2xl overflow-hidden">
          {/* Search input */}
          <div className="flex items-center gap-3 px-4 py-3.5 border-b border-border">
            <Search className="w-4 h-4 text-foreground-3 flex-shrink-0" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => { setQuery(e.target.value); setSelectedIdx(0); }}
              onKeyDown={handleKeyDown}
              placeholder="Search conversations…"
              className="flex-1 bg-transparent text-sm text-foreground placeholder:text-foreground-3 focus:outline-none"
              aria-label="Search conversations"
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                className="p-1 rounded text-foreground-3 hover:text-foreground transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
            <kbd className="kbd hidden sm:inline-flex">Esc</kbd>
          </div>

          {/* Results */}
          <div className="max-h-96 overflow-y-auto">
            {query.trim() ? (
              results.length > 0 ? (
                <div className="py-2">
                  <p className="px-4 py-1 text-[10px] font-bold uppercase tracking-widest text-foreground-3">
                    Conversations
                  </p>
                  {results.map((chat, i) => (
                    <button
                      key={chat.id}
                      onClick={() => handleSelect(chat.id, chat.title)}
                      onMouseEnter={() => setSelectedIdx(i)}
                      className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                        i === selectedIdx ? 'bg-accent/10 text-foreground' : 'text-foreground-2 hover:bg-surface-2'
                      }`}
                    >
                      <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 text-foreground-3" />
                      <span className="text-sm truncate flex-1">
                        {highlight(chat.title || 'New Chat', query)}
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="py-12 text-center text-foreground-3 text-sm">
                  No conversations found for "<span className="text-foreground-2">{query}</span>"
                </div>
              )
            ) : recentSearches.length > 0 ? (
              <div className="py-2">
                <p className="px-4 py-1 text-[10px] font-bold uppercase tracking-widest text-foreground-3 flex items-center gap-1.5">
                  <Clock className="w-3 h-3" /> Recent Searches
                </p>
                {recentSearches.map((r) => (
                  <button
                    key={r}
                    onClick={() => setQuery(r)}
                    className="w-full flex items-center gap-3 px-4 py-2 text-left text-sm text-foreground-2 hover:bg-surface-2 hover:text-foreground transition-colors"
                  >
                    <Clock className="w-3.5 h-3.5 flex-shrink-0 text-foreground-3" />
                    {r}
                  </button>
                ))}
              </div>
            ) : (
              <div className="py-12 text-center text-foreground-3 text-sm">
                Start typing to search conversations
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2.5 border-t border-border bg-surface-2/50 flex items-center gap-4 text-[11px] text-foreground-3">
            <span className="flex items-center gap-1"><kbd className="kbd">↑↓</kbd> Navigate</span>
            <span className="flex items-center gap-1"><kbd className="kbd">↵</kbd> Select</span>
            <span className="flex items-center gap-1"><kbd className="kbd">Esc</kbd> Close</span>
          </div>
        </div>
      </div>
    </>
  );
}
