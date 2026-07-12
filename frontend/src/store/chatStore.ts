import { create } from 'zustand';
import { ChatSession, Message } from '../types/chat';

interface ChatState {
  chats: ChatSession[];
  activeChatId: string | null;
  messages: Message[];
  activeModel: string;
  isStreaming: boolean;
  
  // Actions
  setChats: (chats: ChatSession[]) => void;
  setActiveChatId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  setActiveModel: (model: string) => void;
  setIsStreaming: (streaming: boolean) => void;
  
  addChat: (chat: ChatSession) => void;
  removeChat: (chatId: string) => void;
  updateChat: (chat: ChatSession) => void;
  addMessage: (msg: Message) => void;
  updateLastMessageContent: (content: string) => void;
  updateMessage: (msgId: string, updates: Partial<Message>) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  chats: [],
  activeChatId: null,
  messages: [],
  activeModel: 'gemini-1.5-flash',
  isStreaming: false,

  setChats: (chats) => set({ chats }),
  setActiveChatId: (id) => set({ activeChatId: id, messages: id ? [] : [] }),
  setMessages: (messages) => set({ messages }),
  setActiveModel: (model) => set({ activeModel: model }),
  setIsStreaming: (streaming) => set({ isStreaming: streaming }),

  addChat: (chat) => set((state) => ({ chats: [chat, ...state.chats] })),
  removeChat: (chatId) => set((state) => ({ 
    chats: state.chats.filter((c) => c.id !== chatId),
    activeChatId: state.activeChatId === chatId ? null : state.activeChatId
  })),
  updateChat: (chat) => set((state) => ({
    chats: state.chats.map((c) => c.id === chat.id ? chat : c)
  })),
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  updateLastMessageContent: (content) => set((state) => {
    const nextMsgs = [...state.messages];
    if (nextMsgs.length > 0) {
      nextMsgs[nextMsgs.length - 1] = {
        ...nextMsgs[nextMsgs.length - 1],
        content
      };
    }
    return { messages: nextMsgs };
  }),
  updateMessage: (msgId, updates) => set((state) => ({
    messages: state.messages.map((m) => m.id === msgId ? { ...m, ...updates } : m)
  }))
}));
