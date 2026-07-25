import { create } from 'zustand';
import { ChatSession, Message } from '../types/chat';

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

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  activeChatId: localStorage.getItem('omni_active_chat_id') || null,
  messages: [],
  messageCache: {},
  activeModel: localStorage.getItem('active_model') || '',
  isStreaming: false,
  providers: [],
  verifiedProviders: [],
  keysLoading: true,

  setChats: (chats) => set({ chats }),

  setActiveChatId: (id) => {
    if (id) {
      localStorage.setItem('omni_active_chat_id', id);
      const state = get();
      const cachedMsgs = state.messageCache[id];
      const msgsToKeep = (cachedMsgs && cachedMsgs.length > 0) ? cachedMsgs : (state.activeChatId === id || state.activeChatId === null ? state.messages : []);
      set({
        activeChatId: id,
        messages: msgsToKeep,
        messageCache: msgsToKeep.length > 0 ? { ...state.messageCache, [id]: msgsToKeep } : state.messageCache,
      });
    } else {
      localStorage.removeItem('omni_active_chat_id');
      set({
        activeChatId: null,
        messages: [],
      });
    }
  },

  setMessages: (messages) => {
    const activeId = get().activeChatId;
    set((state) => ({
      messages,
      messageCache: activeId
        ? { ...state.messageCache, [activeId]: messages }
        : state.messageCache,
    }));
  },

  setMessagesForChat: (chatId, messages) => {
    set((state) => ({
      messageCache: { ...state.messageCache, [chatId]: messages },
      messages: state.activeChatId === chatId ? messages : state.messages,
    }));
  },

  hasCachedMessages: (chatId) => {
    const cached = get().messageCache[chatId];
    return Array.isArray(cached) && cached.length > 0;
  },

  setActiveModel: (model) => {
    localStorage.setItem('active_model', model);
    set({ activeModel: model });
  },

  setIsStreaming: (streaming) => set({ isStreaming: streaming }),

  setProviders: (providers) => set({
    providers,
    verifiedProviders: providers.filter(p => p.verified || p.status === 'VERIFIED').map(p => p.id),
  }),

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

  addChat: (chat) => set((state) => ({ chats: [chat, ...state.chats] })),

  removeChat: (chatId) => set((state) => {
    const newCache = { ...state.messageCache };
    delete newCache[chatId];
    return {
      chats: state.chats.filter((c) => c.id !== chatId),
      activeChatId: state.activeChatId === chatId ? null : state.activeChatId,
      messages: state.activeChatId === chatId ? [] : state.messages,
      messageCache: newCache,
    };
  }),

  updateChat: (chat) => set((state) => ({
    chats: state.chats.map((c) => c.id === chat.id ? chat : c)
  })),

  addMessage: (msg) => set((state) => {
    const nextMsgs = [...state.messages, msg];
    const activeId = state.activeChatId;
    return {
      messages: nextMsgs,
      messageCache: activeId
        ? { ...state.messageCache, [activeId]: nextMsgs }
        : state.messageCache,
    };
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
        ? { ...state.messageCache, [activeId]: nextMsgs }
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
