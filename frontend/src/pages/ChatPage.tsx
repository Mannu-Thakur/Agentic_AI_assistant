import React, { useState, useEffect, useRef } from 'react';
import { useChatStore } from '../store/chatStore';
import { useUIStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { apiRequest } from '../services/api';
import { 
  Send, 
  Plus, 
  Trash2, 
  Terminal, 
  Clock, 
  Coins, 
  Database, 
  Bot, 
  User, 
  Sparkles, 
  Cpu,
  ChevronDown,
  Layers,
  X,
  CheckCircle2
} from 'lucide-react';

export default function ChatPage() {
  const { 
    chats, 
    activeChatId, 
    messages, 
    activeModel, 
    isStreaming,
    setChats,
    setActiveChatId,
    setMessages,
    setActiveModel,
    setIsStreaming,
    addChat,
    removeChat,
    addMessage,
    updateLastMessageContent,
    updateMessage
  } = useChatStore();

  const { developerMode, toggleDeveloperMode } = useUIStore();
  const { token } = useAuthStore();
  
  const [input, setInput] = useState('');
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [activeHudTab, setActiveHudTab] = useState<'flow' | 'context' | 'logs'>('flow');

  const assistantMessages = messages.filter(m => m.role === 'assistant');
  const lastAssistantMsg = assistantMessages[assistantMessages.length - 1];

  useEffect(() => {
    if (lastAssistantMsg) {
      if (isStreaming || !selectedMessageId) {
        setSelectedMessageId(lastAssistantMsg.id);
      }
    } else {
      setSelectedMessageId(null);
    }
  }, [messages, isStreaming, lastAssistantMsg]);

  const models = [
    { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash', provider: 'Google', icon: Cpu, desc: 'Fast, lightweight multimodal model' },
    { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', provider: 'Google', icon: Sparkles, desc: 'Highly capable reasoning model' },
    { id: 'llama3-8b-8192', name: 'Llama 3 8B', provider: 'Groq', icon: Terminal, desc: 'High-speed open source model' },
    { id: 'llama3-70b-8192', name: 'Llama 3 70B', provider: 'Groq', icon: Layers, desc: 'Capable open source model' }
  ];

  const currentModelObj = models.find(m => m.id === activeModel) || models[0];

  // Fetch chats on mount
  useEffect(() => {
    apiRequest('/chats')
      .then((data) => setChats(data))
      .catch((err) => console.error('Failed to fetch chats:', err));
  }, [setChats]);

  // Fetch messages when activeChatId changes
  useEffect(() => {
    if (activeChatId) {
      apiRequest(`/chats/${activeChatId}`)
        .then((data) => setMessages(data))
        .catch((err) => console.error('Failed to fetch messages:', err));
    } else {
      setMessages([]);
    }
  }, [activeChatId, setMessages]);

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleCreateChat = async () => {
    try {
      const newChat = await apiRequest('/chats', {
        method: 'POST',
        json: { title: 'New Conversation' }
      });
      addChat(newChat);
      setActiveChatId(newChat.id);
    } catch (err) {
      console.error('Failed to create chat:', err);
    }
  };

  const handleDeleteChat = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiRequest(`/chats/${id}`, { method: 'DELETE' });
      removeChat(id);
    } catch (err) {
      console.error('Failed to delete chat:', err);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    let chatId = activeChatId;
    
    // Create new chat session if none is selected
    if (!chatId) {
      try {
        const newChat = await apiRequest('/chats', {
          method: 'POST',
          json: { title: input.trim().substring(0, 30) }
        });
        addChat(newChat);
        chatId = newChat.id;
        setActiveChatId(chatId);
      } catch (err) {
        console.error('Failed to auto-create chat:', err);
        return;
      }
    }

    const userMsgText = input.trim();
    setInput('');

    // Add user message to state
    const userMsg = {
      id: crypto.randomUUID(),
      chat_id: chatId!,
      parent_id: messages.length > 0 ? messages[messages.length - 1].id : null,
      role: 'user' as const,
      content: userMsgText,
      tool_calls: null,
      developer_metrics: null,
      created_at: new Date().toISOString()
    };
    addMessage(userMsg);

    // Add placeholder assistant message to stream into
    const assistantMsgId = crypto.randomUUID();
    const assistantMsgPlaceholder = {
      id: assistantMsgId,
      chat_id: chatId!,
      parent_id: userMsg.id,
      role: 'assistant' as const,
      content: '',
      tool_calls: null,
      developer_metrics: null,
      created_at: new Date().toISOString()
    };
    addMessage(assistantMsgPlaceholder);
    setIsStreaming(true);
    let assistantText = '';

    try {
      const response = await fetch(`/api/v1/chats/${chatId}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          content: userMsgText,
          model: activeModel,
          parent_message_id: userMsg.parent_id
        })
      });

      if (!response.ok) {
        throw new Error('Streaming connection failed');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      
      if (!reader) {
        throw new Error('No body reader on streaming response');
      }

      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        // Save the last incomplete line back to the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          
          if (trimmed.startsWith('data: ')) {
            const rawData = trimmed.substring(6);
            if (rawData === '[DONE]') continue;
            
            try {
              const parsed = JSON.parse(rawData);
              
              if (parsed.event === 'chunk') {
                assistantText += parsed.text;
                updateLastMessageContent(assistantText);
              } else if (parsed.event === 'metrics') {
                updateMessage(assistantMsgId, {
                  developer_metrics: parsed.metrics
                });
              }
            } catch (err) {
              console.warn('Failed to parse stream event:', trimmed, err);
            }
          }
        }
      }
    } catch (err: any) {
      console.error('Streaming error:', err);
      updateLastMessageContent(assistantText + '\n\n*[Connection lost or error streaming response]*');
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  return (
    <div className="h-full w-full flex overflow-hidden">
      
      {/* Session Navigation Bar */}
      <aside className="w-64 border-r border-border bg-card/20 flex flex-col justify-between hidden lg:flex flex-shrink-0">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <span className="font-semibold text-xs text-muted-foreground uppercase tracking-wider">Conversations</span>
          <button 
            onClick={handleCreateChat}
            className="p-1.5 rounded-lg border border-border bg-secondary/50 text-foreground hover:bg-muted transition-all"
            title="New Conversation"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {chats.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveChatId(c.id)}
              className={`w-full text-left px-3 py-2.5 rounded-xl text-xs font-medium flex items-center justify-between group transition-all ${
                activeChatId === c.id 
                  ? 'bg-secondary text-foreground' 
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary/30'
              }`}
            >
              <span className="truncate pr-2">{c.title || 'New Chat'}</span>
              <button
                onClick={(e) => handleDeleteChat(c.id, e)}
                className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-all"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </button>
          ))}
          {chats.length === 0 && (
            <div className="text-center py-8 text-xs text-muted-foreground">
              No recent chats. Create one!
            </div>
          )}
        </div>
      </aside>

      {/* Main Chat Workspace */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        
        {/* Workspace Toolbar */}
        <header className="h-16 px-6 border-b border-border flex items-center justify-between bg-card/35 backdrop-blur-md z-10 flex-shrink-0">
          <div className="flex items-center space-x-3">
            <span className="font-semibold text-sm truncate">
              {activeChatId ? chats.find(c => c.id === activeChatId)?.title || 'Active Chat' : 'New Chat'}
            </span>
          </div>

          {/* Controls */}
          <div className="flex items-center space-x-3">
            {/* Dev HUD Toggle */}
            <button 
              onClick={toggleDeveloperMode}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all ${
                developerMode 
                  ? 'border-violet-500 bg-violet-500/10 text-violet-400 hover:bg-violet-500/20' 
                  : 'border-border bg-secondary/50 hover:bg-secondary text-muted-foreground hover:text-foreground'
              }`}
              title="Toggle Developer HUD"
            >
              <Terminal className="w-4 h-4" />
              <span className="hidden sm:inline">Dev HUD</span>
            </button>

            <div className="relative">
              <button 
                onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
                className="flex items-center space-x-2 px-3 py-1.5 rounded-xl border border-border bg-secondary/50 hover:bg-secondary text-xs font-semibold transition-all text-foreground"
              >
                <currentModelObj.icon className="w-4 h-4 text-violet-400" />
                <span>{currentModelObj.name}</span>
                <ChevronDown className="w-3 h-3 text-muted-foreground" />
              </button>

              {modelDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setModelDropdownOpen(false)} />
                  <div className="absolute right-0 mt-2 w-64 rounded-2xl border border-border bg-card shadow-2xl p-2 z-50 space-y-1.5 animate-in fade-in slide-in-from-top-2 duration-200">
                  {models.map((m) => {
                    const Icon = m.icon;
                    return (
                      <button
                        key={m.id}
                        onClick={() => {
                          setActiveModel(m.id);
                          setModelDropdownOpen(false);
                        }}
                        className={`w-full text-left p-2 rounded-xl text-xs transition-all flex items-start space-x-2.5 ${
                          activeModel === m.id
                            ? 'bg-primary text-primary-foreground'
                            : 'hover:bg-secondary text-foreground'
                        }`}
                      >
                        <Icon className={`w-4 h-4 mt-0.5 ${activeModel === m.id ? 'text-white' : 'text-violet-400'}`} />
                        <div>
                          <p className="font-semibold">{m.name}</p>
                          <p className={`text-[10px] mt-0.5 ${activeModel === m.id ? 'text-violet-200' : 'text-muted-foreground'}`}>
                            {m.desc}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
            </div>
          </div>
        </header>

        {/* Message Feed Display */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-gradient-to-b from-background to-card/5">
          {messages.map((m) => {
            const isUser = m.role === 'user';
            
            // Skip system or tool messages in basic chat feed (or render specifically)
            if (m.role === 'system' || m.role === 'tool') return null;

            return (
              <div 
                key={m.id} 
                onClick={() => !isUser && setSelectedMessageId(m.id)}
                className={`flex space-x-4 max-w-3xl transition-all duration-200 ${
                  isUser ? 'ml-auto flex-row-reverse space-x-reverse' : 'mr-auto'
                } ${
                  !isUser && developerMode ? 'cursor-pointer hover:bg-secondary/10 p-2 rounded-3xl -mx-2' : ''
                } ${
                  !isUser && developerMode && selectedMessageId === m.id ? 'ring-2 ring-violet-500/40 bg-violet-500/5' : ''
                }`}
              >
                {/* Avatar */}
                <div className={`w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center font-semibold text-white shadow-md ${
                  isUser 
                    ? 'bg-gradient-to-tr from-violet-600 to-indigo-600 shadow-violet-900/10' 
                    : 'bg-gradient-to-tr from-emerald-600 to-teal-600 shadow-emerald-900/10'
                }`}>
                  {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>

                {/* Bubble */}
                <div className="space-y-2 max-w-[85%]">
                  <div className={`rounded-3xl p-4.5 text-sm leading-relaxed shadow-sm border ${
                    isUser 
                      ? 'bg-primary text-primary-foreground border-primary/20 rounded-tr-none' 
                      : 'bg-card/50 text-foreground border-border rounded-tl-none'
                  }`}>
                    {/* Render message formatting */}
                    <div className="whitespace-pre-wrap break-words">
                      {m.content || (isStreaming && messages[messages.length - 1].id === m.id ? 'Thinking...' : '')}
                    </div>
                  </div>

                  {/* Dev mode HUD panel for this specific assistant response */}
                  {!isUser && developerMode && m.developer_metrics && (
                    <div className="p-3.5 rounded-2xl border border-border bg-card/60 space-y-2.5 text-[10px] text-muted-foreground font-mono max-w-md shadow-inner animate-in fade-in duration-300">
                      <div className="flex items-center space-x-1 border-b border-border/50 pb-1.5 text-violet-400 font-semibold uppercase tracking-wider">
                        <Terminal className="w-3.5 h-3.5" />
                        <span>Execution Telemetry HUD</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="flex items-center space-x-1.5">
                          <Cpu className="w-3 h-3 text-muted-foreground" />
                          <span>Model: <span className="text-foreground">{m.developer_metrics.model_used}</span></span>
                        </div>
                        <div className="flex items-center space-x-1.5">
                          <Clock className="w-3 h-3 text-muted-foreground" />
                          <span>Latency: <span className="text-foreground">{m.developer_metrics.latency_ms}ms</span></span>
                        </div>
                        <div className="flex items-center space-x-1.5">
                          <Coins className="w-3 h-3 text-muted-foreground" />
                          <span>Tokens: <span className="text-foreground">{m.developer_metrics.tokens_input} in / {m.developer_metrics.tokens_output} out</span></span>
                        </div>
                        <div className="flex items-center space-x-1.5">
                          <Database className="w-3 h-3 text-muted-foreground" />
                          <span>Memory Hits: <span className="text-foreground">{m.developer_metrics.memory_hits} records</span></span>
                        </div>
                      </div>
                      {m.developer_metrics.search_queries && m.developer_metrics.search_queries.length > 0 && (
                        <div className="border-t border-border/50 pt-1.5">
                          <span className="text-violet-400/80 font-semibold uppercase">Tavily Web Search:</span>
                          <ul className="list-disc list-inside mt-1 space-y-0.5 text-[9px]">
                            {m.developer_metrics.search_queries.map((q, idx) => (
                              <li key={idx} className="truncate text-foreground/80">{q}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center space-y-4 max-w-md mx-auto pt-16">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-violet-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-900/20">
                <Bot className="w-6 h-6 text-white" />
              </div>
              <h2 className="text-lg font-bold">Initiate Flagship AI Session</h2>
              <p className="text-muted-foreground text-xs leading-relaxed">
                Choose a model on the top right, write your request below, and the LangGraph orchestrator will trigger adaptive routing.
              </p>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar Section */}
        <footer className="p-4 border-t border-border bg-card/25 backdrop-blur-md flex-shrink-0">
          <form onSubmit={handleSendMessage} className="max-w-3xl mx-auto flex items-end space-x-3">
            <div className="flex-1 relative rounded-2xl border border-border bg-secondary/20 focus-within:border-primary transition-all p-1.5 flex">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask your assistant anything..."
                rows={1}
                className="w-full bg-transparent resize-none py-2 px-3 focus:outline-none text-sm text-foreground placeholder-muted-foreground leading-relaxed max-h-32"
                style={{ height: 'auto' }}
              />
            </div>
            <button
              type="submit"
              disabled={!input.trim() || isStreaming}
              className="p-3 rounded-2xl bg-primary text-primary-foreground hover:opacity-95 disabled:opacity-50 transition-all shadow-lg shadow-primary/20 flex-shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <div className="text-center text-[10px] text-muted-foreground mt-2 font-medium">
            Shift+Enter for newline. Responses are compiled and verified by Omni systems.
          </div>
        </footer>

      </div>

      {/* DevHUD Panel */}
      {developerMode && (
        <aside className="w-[420px] border-l border-border bg-card flex flex-col flex-shrink-0 z-20 animate-in slide-in-from-right duration-300">
          <div className="h-16 px-6 border-b border-border flex items-center justify-between flex-shrink-0 bg-secondary/20">
            <div className="flex items-center space-x-2">
              <Terminal className="w-4.5 h-4.5 text-violet-400" />
              <span className="font-semibold text-sm">Execution Telemetry HUD</span>
            </div>
            <button 
              onClick={toggleDeveloperMode}
              className="p-1 rounded-lg hover:bg-secondary text-muted-foreground hover:text-foreground transition-all"
              title="Close Dev HUD"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            {(() => {
              const selectedMsg = messages.find(m => m.id === selectedMessageId);
              if (!selectedMsg) {
                return (
                  <div className="h-full flex flex-col items-center justify-center text-center p-6 text-muted-foreground space-y-3">
                    <Database className="w-8 h-8 text-muted-foreground/45" />
                    <p className="text-xs">Select an assistant response from the chat to inspect its telemetry.</p>
                  </div>
                );
              }

              const metrics = selectedMsg.developer_metrics;
              if (!metrics) {
                return (
                  <div className="p-6 text-center text-xs text-muted-foreground space-y-2">
                    <p>No telemetry recorded for this message.</p>
                    <p className="text-[10px] text-muted-foreground/60">This can occur if the message was sent before DevHUD was enabled or if metrics collection failed.</p>
                  </div>
                );
              }

              const steps = metrics.steps || ['retrieve_context', 'generate_response'];
              const hasTools = selectedMsg.tool_calls && selectedMsg.tool_calls.length > 0;

              return (
                <div className="space-y-6">
                  {/* Grid metrics */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 rounded-2xl border border-border bg-secondary/10 space-y-1">
                      <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Model Used</span>
                      <p className="text-xs font-bold text-foreground truncate">{metrics.model_used}</p>
                    </div>
                    <div className="p-3 rounded-2xl border border-border bg-secondary/10 space-y-1">
                      <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Latency</span>
                      <p className="text-xs font-bold text-foreground">{metrics.latency_ms >= 1000 ? `${(metrics.latency_ms / 1000).toFixed(2)}s` : `${metrics.latency_ms}ms`}</p>
                    </div>
                    <div className="p-3 rounded-2xl border border-border bg-secondary/10 space-y-1">
                      <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Token Count</span>
                      <p className="text-xs font-bold text-foreground leading-tight">{metrics.tokens_input} in / {metrics.tokens_output} out</p>
                    </div>
                    <div className="p-3 rounded-2xl border border-border bg-secondary/10 space-y-1">
                      <span className="text-[9px] text-muted-foreground font-semibold uppercase tracking-wider">Est. Cost</span>
                      <p className="text-xs font-bold text-emerald-400 font-mono">${metrics.cost_estimate?.toFixed(6) || '0.000000'}</p>
                    </div>
                  </div>

                  {/* HUD Inner Navigation tabs */}
                  <div className="flex border-b border-border">
                    <button 
                      onClick={() => setActiveHudTab('flow')}
                      className={`flex-1 pb-2 text-[10px] font-bold uppercase tracking-wider border-b-2 text-center transition-all ${
                        activeHudTab === 'flow' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      Execution Flow
                    </button>
                    <button 
                      onClick={() => setActiveHudTab('context')}
                      className={`flex-1 pb-2 text-[10px] font-bold uppercase tracking-wider border-b-2 text-center transition-all ${
                        activeHudTab === 'context' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      Context Inspector
                    </button>
                    <button 
                      onClick={() => setActiveHudTab('logs')}
                      className={`flex-1 pb-2 text-[10px] font-bold uppercase tracking-wider border-b-2 text-center transition-all ${
                        activeHudTab === 'logs' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      Tools & Logs
                    </button>
                  </div>

                  {/* Tab Contents */}
                  {activeHudTab === 'flow' && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">LangGraph Execution Path</span>
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[9px] font-semibold bg-violet-500/10 text-violet-400 border border-violet-500/20">
                          Active State Machine
                        </span>
                      </div>

                      {/* Visual Stepper */}
                      <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border/60">
                        {/* 1. Retrieve Context Node */}
                        <div className="relative">
                          <div className={`absolute -left-6 w-5.5 h-5.5 rounded-full border flex items-center justify-center bg-card transition-all ${
                            steps.includes('retrieve_context') ? 'border-primary text-primary shadow-sm shadow-primary/20 bg-primary/5' : 'border-border text-muted-foreground'
                          }`}>
                            <Database className="w-3 h-3" />
                          </div>
                          <div className="space-y-1">
                            <h4 className="text-xs font-semibold">retrieve_context</h4>
                            <p className="text-[10px] text-muted-foreground leading-relaxed">
                              ChromaDB RAG query executed & long-term episodic user preferences retrieved.
                            </p>
                            <span className="text-[9px] text-primary/80 font-semibold font-mono">
                              Hits: {metrics.memory_hits} memory / {metrics.chunks_used || 0} doc chunks
                            </span>
                          </div>
                        </div>

                        {/* 2. Generate Response Node (1st pass) */}
                        <div className="relative">
                          <div className={`absolute -left-6 w-5.5 h-5.5 rounded-full border flex items-center justify-center bg-card transition-all ${
                            steps.includes('generate_response') ? 'border-primary text-primary shadow-sm shadow-primary/20 bg-primary/5' : 'border-border text-muted-foreground'
                          }`}>
                            <Cpu className="w-3 h-3" />
                          </div>
                          <div className="space-y-1">
                            <h4 className="text-xs font-semibold">generate_response</h4>
                            <p className="text-[10px] text-muted-foreground leading-relaxed">
                              LLM processed injected context and initialized reply generation.
                            </p>
                          </div>
                        </div>

                        {/* 3. Execute Tools Node (Conditional) */}
                        <div className="relative">
                          <div className={`absolute -left-6 w-5.5 h-5.5 rounded-full border flex items-center justify-center bg-card transition-all ${
                            steps.includes('execute_tools') || hasTools ? 'border-emerald-500 text-emerald-400 shadow-sm shadow-emerald-500/20 bg-emerald-500/5' : 'border-border text-muted-foreground opacity-60'
                          }`}>
                            <Terminal className="w-3 h-3" />
                          </div>
                          <div className="space-y-1">
                            <div className="flex items-center space-x-1.5">
                              <h4 className="text-xs font-semibold">execute_tools</h4>
                              {!hasTools && <span className="text-[8px] text-muted-foreground font-semibold">(Skipped)</span>}
                            </div>
                            <p className="text-[10px] text-muted-foreground leading-relaxed">
                              Executed local tools or routed requests through MCP server protocols.
                            </p>
                            {selectedMsg.tool_calls && selectedMsg.tool_calls.length > 0 && (
                              <div className="mt-2 p-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 text-[9px] font-mono text-emerald-400 space-y-1 max-w-sm">
                                {selectedMsg.tool_calls.map((tc, idx) => (
                                  <div key={idx} className="truncate">
                                    &bull; <strong>{tc.name}</strong>({JSON.stringify(tc.args)})
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* 4. Final Synthesize Node */}
                        <div className="relative">
                          <div className={`absolute -left-6 w-5.5 h-5.5 rounded-full border flex items-center justify-center bg-card transition-all ${
                            steps.filter(x => x === 'generate_response').length > 1 ? 'border-primary text-primary shadow-sm shadow-primary/20 bg-primary/5' : 'border-border text-muted-foreground opacity-60'
                          }`}>
                            <Sparkles className="w-3 h-3" />
                          </div>
                          <div className="space-y-1">
                            <div className="flex items-center space-x-1.5">
                              <h4 className="text-xs font-semibold">generate_response (consolidated)</h4>
                              {steps.filter(x => x === 'generate_response').length <= 1 && <span className="text-[8px] text-muted-foreground font-semibold">(Skipped)</span>}
                            </div>
                            <p className="text-[10px] text-muted-foreground leading-relaxed">
                              Final synthesis combining tool feedback into cohesive markdown stream.
                            </p>
                          </div>
                        </div>

                      </div>
                    </div>
                  )}

                  {activeHudTab === 'context' && (
                    <div className="space-y-5">
                      <div>
                        <h4 className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider mb-2.5">Retrieved Prompt Context</h4>
                        
                        <div className="space-y-3">
                          {metrics.retrieved_context && metrics.retrieved_context.length > 0 ? (
                            metrics.retrieved_context.map((item, idx) => {
                              const isMemory = item.type === 'memory';
                              return (
                                <div key={idx} className="p-3 rounded-xl border border-border bg-card text-[10px] space-y-1.5 shadow-sm">
                                  <div className="flex items-center justify-between">
                                    <span className={`px-2 py-0.5 rounded-full text-[8px] font-bold uppercase ${
                                      isMemory 
                                        ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20' 
                                        : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                                    }`}>
                                      {isMemory ? `Memory: ${item.category || 'fact'}` : 'RAG Chunk'}
                                    </span>
                                    {!isMemory && item.distance !== undefined && (
                                      <span className="text-[8px] text-muted-foreground font-mono">
                                        Dist: {item.distance.toFixed(4)}
                                      </span>
                                    )}
                                    {isMemory && item.importance_score !== undefined && (
                                      <span className="text-[8px] text-yellow-400 flex items-center space-x-0.5">
                                        <Sparkles className="w-2.5 h-2.5" />
                                        <span>Score: {item.importance_score}/10</span>
                                      </span>
                                    )}
                                  </div>
                                  
                                  {!isMemory && (
                                    <p className="font-semibold text-foreground truncate">File: {item.filename}</p>
                                  )}
                                  <p className="text-muted-foreground leading-relaxed font-mono whitespace-pre-wrap break-all border-l-2 border-border/80 pl-2">
                                    {item.content}
                                  </p>
                                </div>
                              );
                            })
                          ) : (
                            <div className="text-center py-6 border border-dashed border-border rounded-xl text-muted-foreground bg-card/20">
                              No retrieval context injected.
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {activeHudTab === 'logs' && (
                    <div className="space-y-4">
                      {metrics.search_queries && metrics.search_queries.length > 0 && (
                        <div>
                          <h4 className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider mb-2">Tavily Web Search Queries</h4>
                          <div className="p-3 rounded-xl border border-border bg-card font-mono text-[10px] space-y-1">
                            {metrics.search_queries.map((q, idx) => (
                              <div key={idx} className="text-foreground/90">
                                &gt; Tavily search for: <span className="text-violet-400 font-semibold font-sans">"{q}"</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div>
                        <h4 className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider mb-2">Automatic Memory Pipeline Log</h4>
                        <div className="p-3 rounded-xl border border-border bg-card font-mono text-[9px] text-muted-foreground space-y-2 leading-relaxed">
                          <div className="flex items-center space-x-1.5 text-emerald-400 font-sans">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span className="font-semibold">Pipeline Execution Success</span>
                          </div>
                          <div>
                            <span className="text-foreground font-semibold">&gt; Scanning interaction for facts/preferences...</span>
                          </div>
                          <div>
                            &bull; Categorized exchange: user query context scanned.
                          </div>
                          <div>
                            &bull; Deduplication registry checked against current user cache.
                          </div>
                          <div className="border-t border-border/30 pt-2 text-[8px] text-muted-foreground/60 font-sans">
                            Updates are applied asynchronously to the ingestion hub and immediately loaded into subsequent conversation windows.
                          </div>
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
