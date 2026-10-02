import { create } from 'zustand';
import { ChatSession, Message } from '../types/chat';

function safeSetItem(key: string, val: string) {
  try {
    localStorage.setItem(key, val);
  } catch (e) {
    console.warn(`[chatStore] Failed to write ${key} to localStorage:`, e);
  }
}

// BUG-13 FIX: Cap the in-memory message cache at MAX_CACHED_CHATS entries.
// Without eviction, each chat switch accumulates serialized message history
// indefinitely, eventually OOM-ing the browser tab in long sessions.
const MAX_CACHED_CHATS = 10;

function evictMessageCache(
  cache: Record<string, any[]>,
  activeId: string | null
): Record<string, any[]> {
  const keys = Object.keys(cache);
  if (keys.length <= MAX_CACHED_CHATS) return cache;
  // Keep the active chat and the N-1 most recently added keys
  const evicted = { ...cache };
  const toRemove = keys
    .filter((k) => k !== activeId)
    .slice(0, keys.length - MAX_CACHED_CHATS);
  toRemove.forEach((k) => delete evicted[k]);
  return evicted;
}

export interface Provider {
  id: string;
  status: 'VERIFIED' | 'INVALID' | 'UNCONFIGURED' | 'VERIFYING' | 'ERROR' | string;
  saved: boolean;
  verified: boolean;
  enabled: boolean;
  lastChecked: string | null;
  availableModels: string[];
  lastError?: string | null;
}

interface ChatState {
  chats: ChatSession[];
  activeChatId: string | null;
  messages: Message[];
  messageCache: Record<string, Message[]>;
  activeModel: string;
  isStreaming: boolean;

  providers: Provider[];
  verifiedProviders: string[];
  keysLoading: boolean;

  // Actions
  setChats: (chats: ChatSession[]) => void;
  setActiveChatId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  setMessagesForChat: (chatId: string, messages: Message[]) => void;
  hasCachedMessages: (chatId: string) => boolean;
  setActiveModel: (model: string) => void;
  setIsStreaming: (streaming: boolean) => void;
  
  setProviders: (providers: Provider[]) => void;
  updateProvider: (id: string, updates: Partial<Provider>) => void;
  setVerifiedProviders: (providers: string[]) => void;
  addVerifiedProvider: (provider: string) => void;
  removeVerifiedProvider: (provider: string) => void;
  setKeysLoading: (loading: boolean) => void;

  addChat: (chat: ChatSession) => void;
  removeChat: (chatId: string) => void;
  updateChat: (chat: ChatSession) => void;
  addMessage: (msg: Message) => void;
  updateLastMessageContent: (content: string) => void;
  updateMessage: (msgId: string, updates: Partial<Message>) => void;
}

export function getChatTimestamp(c: ChatSession | any): number {
  if (!c) return 0;
  const rawDate = c.updated_at || c.created_at;
  if (!rawDate) return 0;
  let s = String(rawDate).trim();
  if (!s.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(s)) {
    s = s.replace(' ', 'T');
    if (!s.includes('T')) s += 'T00:00:00Z';
    else s += 'Z';
  }
  const time = new Date(s).getTime();
  return isNaN(time) ? 0 : time;
}

function _loadCachedProviders(): Provider[] {
  try {
    const raw = localStorage.getItem('omni_providers_cache');
    if (raw) return JSON.parse(raw) as Provider[];
  } catch { /* ignore */ }
  return [];
}

const _cachedProviders = _loadCachedProviders();

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  activeChatId: localStorage.getItem('omni_active_chat_id') || null,
  messages: [],
  messageCache: {},
  activeModel: localStorage.getItem('active_model') || '',
  isStreaming: false,
  // Hydrate from localStorage cache — keysLoading is only true when there's no cache yet
  providers: _cachedProviders,
  verifiedProviders: _cachedProviders
    .filter(p => p.verified || p.status === 'VERIFIED')
    .map(p => p.id),
  keysLoading: _cachedProviders.length === 0,

  setChats: (chats) => set({
    chats: [...chats].sort((a, b) => getChatTimestamp(b) - getChatTimestamp(a))
  }),

  setActiveChatId: (id) => set((state) => {
    if (id) {
      localStorage.setItem('omni_active_chat_id', id);
      const cachedMsgs = state.messageCache[id];
      const isSameOrNewSession = state.activeChatId === id || state.activeChatId === null || state.activeChatId?.startsWith('temp-');
      const msgsToKeep = (cachedMsgs && cachedMsgs.length > 0)
        ? cachedMsgs
        : (isSameOrNewSession && state.messages.length > 0 ? state.messages : []);
      const keepStreaming = isSameOrNewSession ? state.isStreaming : false;
      return {
        activeChatId: id,
        messages: msgsToKeep,
        isStreaming: keepStreaming,
        messageCache: (cachedMsgs && cachedMsgs.length > 0)
          ? state.messageCache
          : (msgsToKeep.length > 0 ? { ...state.messageCache, [id]: msgsToKeep } : state.messageCache),
      };
    } else {
      localStorage.removeItem('omni_active_chat_id');
      return {
        activeChatId: null,
        messages: [],
        isStreaming: false,
      };
    }
  }),

  setMessages: (messages) => {
    const activeId = get().activeChatId;
    set((state) => {
      const nextCache = activeId
        ? evictMessageCache({ ...state.messageCache, [activeId]: messages }, activeId)
        : state.messageCache;
      return { messages, messageCache: nextCache };
    });
  },

  setMessagesForChat: (chatId, messages) => {
    set((state) => {
      const nextCache = evictMessageCache(
        { ...state.messageCache, [chatId]: messages },
        state.activeChatId
      );
      return {
        messageCache: nextCache,
        messages: state.activeChatId === chatId ? messages : state.messages,
      };
    });
  },

  hasCachedMessages: (chatId) => {
    const cached = get().messageCache[chatId];
    return Array.isArray(cached) && cached.length > 0;
  },

  setActiveModel: (model) => {
    safeSetItem('active_model', model);
    set({ activeModel: model });
  },

  setIsStreaming: (streaming) => set({ isStreaming: streaming }),

  setProviders: (providers) => {
    // Security hardening: sanitize sensitive credentials before writing to localStorage
    const sanitized = providers.map((p: any) => {
      const copy = { ...p };
      delete copy.api_key;
      delete copy.apiKey;
      delete copy.secret;
      delete copy.token;
      delete copy.credentials;
      return copy;
    });
    safeSetItem('omni_providers_cache', JSON.stringify(sanitized));
    set({
      providers,
      verifiedProviders: providers.filter(p => p.verified || p.status === 'VERIFIED').map(p => p.id),
    });
  },

  updateProvider: (id, updates) => {
    set((state) => {
      const nextProviders = state.providers.map((p) =>
        p.id === id ? { ...p, ...updates } : p
      );
      const sanitized = nextProviders.map((p: any) => {
        const copy = { ...p };
        delete copy.api_key;
        delete copy.apiKey;
        delete copy.secret;
        delete copy.token;
        delete copy.credentials;
        return copy;
      });
      safeSetItem('omni_providers_cache', JSON.stringify(sanitized));
      return {
        providers: nextProviders,
        verifiedProviders: nextProviders
          .filter((p) => p.verified || p.status === 'VERIFIED')
          .map((p) => p.id),
      };
    });
  },

  setVerifiedProviders: (providers) => set({ verifiedProviders: providers }),

  addVerifiedProvider: (provider) =>
    set((state) => ({
      verifiedProviders: state.verifiedProviders.includes(provider)
        ? state.verifiedProviders
        : [...state.verifiedProviders, provider],
    })),

  removeVerifiedProvider: (provider) =>
    set((state) => ({
      verifiedProviders: state.verifiedProviders.filter((p) => p !== provider),
    })),

  setKeysLoading: (loading) => set({ keysLoading: loading }),

  addChat: (chat) => set((state) => {
    const otherChats = state.chats.filter((c) => c.id !== chat.id);
    const nextChats = [chat, ...otherChats].sort((a, b) => getChatTimestamp(b) - getChatTimestamp(a));
    return { chats: nextChats };
  }),

  removeChat: (chatId) => set((state) => {
    const isDeletingActive = state.activeChatId === chatId;
    const newCache = { ...state.messageCache };
    delete newCache[chatId];
    if (isDeletingActive) {
      try { localStorage.removeItem('omni_active_chat_id'); } catch { /* ignore */ }
    }
    return {
      chats: state.chats.filter((c) => c.id !== chatId),
      activeChatId: isDeletingActive ? null : state.activeChatId,
      messages: isDeletingActive ? [] : state.messages,
      isStreaming: isDeletingActive ? false : state.isStreaming,
      messageCache: newCache,
    };
  }),

  updateChat: (chat) => set((state) => {
    const otherChats = state.chats.filter((c) => c.id !== chat.id);
    const nextChats = [chat, ...otherChats].sort((a, b) => getChatTimestamp(b) - getChatTimestamp(a));
    return { chats: nextChats };
  }),

  addMessage: (msg) => set((state) => {
    const nextMsgs = [...state.messages, msg];
    const activeId = state.activeChatId || (msg.chat_id && !msg.chat_id.startsWith('temp-') ? msg.chat_id : null);
    const nextCache = activeId
      ? evictMessageCache({ ...state.messageCache, [activeId]: nextMsgs }, activeId)
      : state.messageCache;
    return { messages: nextMsgs, messageCache: nextCache };
  }),

  updateLastMessageContent: (content) => set((state) => {
    const nextMsgs = [...state.messages];
    if (nextMsgs.length > 0) {
      nextMsgs[nextMsgs.length - 1] = {
        ...nextMsgs[nextMsgs.length - 1],
        content
      };
    }
    const activeId = state.activeChatId;
    return {
      messages: nextMsgs,
      messageCache: activeId
        ? evictMessageCache({ ...state.messageCache, [activeId]: nextMsgs }, activeId)
        : state.messageCache,
    };
  }),

  updateMessage: (msgId, updates) => set((state) => {
    const nextMsgs = state.messages.map((m) => m.id === msgId ? { ...m, ...updates } : m);
    const activeId = state.activeChatId;
    return {
      messages: nextMsgs,
      messageCache: activeId
        ? { ...state.messageCache, [activeId]: nextMsgs }
        : state.messageCache,
    };
  }),
}));
