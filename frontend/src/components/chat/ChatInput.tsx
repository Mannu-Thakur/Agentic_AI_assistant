import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Plus, Mic, ArrowUp, Square, FileText, X, Eye, Undo2, Sparkles, Link, GitBranch, Search, MessageSquare, Image as ImageIcon, Globe, Sliders } from 'lucide-react';
import { useUIStore } from '../../store/uiStore';
import { AdvancedTogglesModal } from './AdvancedTogglesModal';

/** Models (or model-name fragments) known to support vision / image input. */
const VISION_MODEL_FRAGMENTS = [
  // Google / Gemini
  'gemini', 'google',
  // OpenAI
  'gpt-4o', 'gpt-4-vision', 'gpt-4.1', 'o1', 'o3', 'o4',
  // Anthropic
  'claude-3', 'claude-3-5', 'claude-4',
  // Meta Llama vision
  'llama-3.2', 'llama-4', 'llama4',
  // DeepSeek vision
  'deepseek-v3', 'deepseek-vl',
  // Alibaba Qwen vision
  'qwen-vl', 'qwen2-vl', 'qwen2.5-vl', 'qvq',
  // Mistral
  'pixtral', 'mistral-large',
  // LLaVA
  'llava',
  // GLM / InternVL
  'glm-4v', 'internvl',
  // Generic vision keywords (catch-all)
  '-vision', '-vl',
  // OpenRouter vendor prefix shortcuts
  'openrouter/google', 'openrouter/anthropic', 'openrouter/openai',
  'openrouter/meta-llama', 'openrouter/mistralai', 'openrouter/qwen',
];

function supportsVision(model: string): boolean {
  const m = model.toLowerCase();
  return VISION_MODEL_FRAGMENTS.some((fragment) => m.includes(fragment));
}

export interface AttachmentItem {
  id: string;
  file: File;
  base64?: string;
  mimeType?: string;
  progress: number;
  status: 'uploading' | 'done' | 'error';
  previewUrl?: string;
  isTextSnippet?: boolean;
  textContent?: string;
  charCount?: number;
  wordCount?: number;
}

interface ChatInputProps {
  onSend: (text: string, images: { base64: string; mimeType: string }[], attachedFiles?: File[]) => void;
  isLocked: boolean;
  isStreaming: boolean;
  onStop: () => void;
  activeModel?: string;
  onOpenShortcuts?: () => void;
  placeholder?: string;
  className?: string;
  chats?: { id: string; title?: string; created_at?: string }[];
  connectedChat?: { id: string; title: string } | null;
  onSelectConnectedChat?: (chat: { id: string; title: string } | null) => void;
}

export const ChatInput = React.memo(function ChatInput({
  onSend,
  isLocked,
  isStreaming,
  onStop,
  activeModel = '',
  placeholder = 'Ask anything',
  className = '',
  chats = [],
  connectedChat = null,
  onSelectConnectedChat,
}: ChatInputProps) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<AttachmentItem[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [viewingSnippet, setViewingSnippet] = useState<AttachmentItem | null>(null);
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [showPlusMenu, setShowPlusMenu] = useState(false);
  const [showAdvancedModal, setShowAdvancedModal] = useState(false);
  const [connectSearch, setConnectSearch] = useState('');
  const [toggles, setToggles] = useState({
    webSearch: true,
    canvas: true,
    voice: true,
    connectorSearch: true,
  });

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const plusMenuRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const interimTextRef = useRef('');
  const isSubmittingRef = useRef(false);

  // Close plus menu on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (plusMenuRef.current && !plusMenuRef.current.contains(e.target as Node)) {
        setShowPlusMenu(false);
      }
    };
    if (showPlusMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showPlusMenu]);

  const enableDictation = useUIStore((s) => s.enableDictation);
  const voiceSupported =
    typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window);

  // Textarea auto-resize
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
  }, [text]);

  // Convert raw text string into a snippet attachment
  const convertTextToAttachment = useCallback((rawText: string) => {
    const trimmed = rawText.trim();
    if (!trimmed) return;
    const firstLine = trimmed.split('\n')[0].replace(/[^a-zA-Z0-9 _-]/g, '').trim();
    const name = (firstLine ? firstLine.slice(0, 24) : 'text-snippet') + '.txt';
    const file = new File([trimmed], name, { type: 'text/plain' });
    const item: AttachmentItem = {
      id: crypto.randomUUID(),
      file,
      mimeType: 'text/plain',
      progress: 100,
      status: 'done',
      isTextSnippet: true,
      textContent: trimmed,
      charCount: trimmed.length,
      wordCount: trimmed.split(/\s+/).filter(Boolean).length,
    };
    setAttachments((prev) => [...prev, item]);
  }, []);

  // Intercept long paste events & clipboard image paste
  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      // ── 1. Image paste from clipboard (screenshot / copied photo / file manager) ──
      const clipboardFiles = Array.from(e.clipboardData.files || []);
      const clipboardItems = Array.from(e.clipboardData.items || []);
      const imageFiles: File[] = [];

      for (const file of clipboardFiles) {
        if (file.type.startsWith('image/')) imageFiles.push(file);
      }
      if (imageFiles.length === 0) {
        for (const item of clipboardItems) {
          if (item.type.startsWith('image/')) {
            const f = item.getAsFile();
            if (f) imageFiles.push(f);
          }
        }
      }

      if (imageFiles.length > 0) {
        e.preventDefault();
        imageFiles.forEach((file) => {
          const ext = file.type.split('/')[1] || 'png';
          const named = file.name ? file : new File(
            [file],
            `pasted-image-${Date.now()}.${ext}`,
            { type: file.type }
          );
          const previewUrl = URL.createObjectURL(named);
          const item: AttachmentItem = {
            id: crypto.randomUUID(),
            file: named,
            mimeType: named.type,
            progress: 0,
            status: 'uploading',
            previewUrl,
          };
          setAttachments((prev) => [...prev, item]);

          const reader = new FileReader();
          reader.onload = (ev) => {
            const result = ev.target?.result as string;
            const base64 = result ? result.split(',')[1] : '';
            setAttachments((prev) =>
              prev.map((att) =>
                att.id === item.id
                  ? { ...att, base64, progress: 100, status: 'done' }
                  : att
              )
            );
          };
          reader.readAsDataURL(named);
        });
        return;
      }

      // ── 2. Long text → convert to snippet attachment ──
      const pasted = e.clipboardData.getData('text');
      if (pasted && (pasted.length > 350 || pasted.split('\n').length > 5)) {
        e.preventDefault();
        convertTextToAttachment(pasted);
      }
    },
    [convertTextToAttachment]
  );

  // Handle Form / Key Submission
  const handleSubmit = useCallback(
    (e?: React.FormEvent) => {
      e?.preventDefault();
      if (isSubmittingRef.current || isStreaming || isLocked) return;

      const trimmed = text.trim();
      if (!trimmed && attachments.length === 0) return;

      // Vision model check — warn if the active model likely doesn't support images,
      // but don't hard-block so power users can still attempt the request.
      const readyImages = attachments.filter((a) => a.status === 'done' && a.base64);
      if (readyImages.length > 0 && activeModel && !supportsVision(activeModel)) {
        const proceed = window.confirm(
          `"${activeModel}" may not support image analysis.\n\nVision-capable models include Gemini, GPT-4o, Claude 3+, and others.\n\nSend anyway?`
        );
        if (!proceed) return;
      }

      isSubmittingRef.current = true;

      // Capture images
      const imagesToSend = readyImages.map((a) => ({
        base64: a.base64!,
        mimeType: a.mimeType!,
      }));

      // Assemble text snippet attachments into payload
      let finalPrompt = trimmed;
      const textSnippets = attachments.filter((a) => a.isTextSnippet && a.textContent);
      if (textSnippets.length > 0) {
        const snippetPayload = textSnippets
          .map((s) => `[Attached File: ${s.file.name}]\n\`\`\`\n${s.textContent}\n\`\`\``)
          .join('\n\n');
        finalPrompt = finalPrompt ? `${finalPrompt}\n\n${snippetPayload}` : snippetPayload;
      }

      // Capture non-image document files attached by user
      const attachedFiles = attachments
        .filter((a) => !a.base64 && !a.isTextSnippet && a.file)
        .map((a) => a.file);

      // Synchronously clear input and attachments
      setText('');
      setAttachments([]);

      // Submit prompt and files to parent
      onSend(finalPrompt, imagesToSend, attachedFiles);

      // Reset submission guard
      setTimeout(() => {
        isSubmittingRef.current = false;
      }, 50);
    },
    [text, attachments, isStreaming, isLocked, activeModel, onSend]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // File Attachments Handler
  const processFiles = (files: FileList) => {
    const MAX_SIZE = 10 * 1024 * 1024; // 10MB limit
    const nextItems: AttachmentItem[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (file.size > MAX_SIZE) {
        alert(`${file.name} exceeds maximum allowed size (10 MB).`);
        continue;
      }
      const isImg = file.type.startsWith('image/');
      const item: AttachmentItem = {
        id: crypto.randomUUID(),
        file,
        mimeType: isImg ? file.type : undefined,
        progress: 0,
        status: 'uploading',
        previewUrl: isImg ? URL.createObjectURL(file) : undefined,
      };
      nextItems.push(item);

      if (isImg) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const result = ev.target?.result as string;
          const base64 = result ? result.split(',')[1] : '';
          setAttachments((prev) =>
            prev.map((att) =>
              att.id === item.id ? { ...att, base64, progress: 100, status: 'done' } : att
            )
          );
        };
        reader.readAsDataURL(file);
      } else {
        let p = 0;
        const interval = setInterval(() => {
          p += 25;
          setAttachments((prev) =>
            prev.map((att) =>
              att.id === item.id
                ? { ...att, progress: Math.min(p, 100), status: p >= 100 ? 'done' : 'uploading' }
                : att
            )
          );
          if (p >= 100) clearInterval(interval);
        }, 100);
      }
    }
    setAttachments((prev) => [...prev, ...nextItems]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files);
      e.target.value = '';
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const item = prev.find((a) => a.id === id);
      if (item?.previewUrl) {
        URL.revokeObjectURL(item.previewUrl);
      }
      return prev.filter((a) => a.id !== id);
    });
  };

  // Web Speech API / Voice Dictation
  const handleToggleMic = () => {
    if (!voiceSupported) return;
    if (isListening) {
      recognitionRef.current?.stop();
      return;
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      alert('Voice dictation is not supported in this browser. Please try Google Chrome or Edge.');
      return;
    }

    try {
      const recognition = new SR();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      interimTextRef.current = text;

      recognition.onstart = () => setIsListening(true);
      recognition.onresult = (event: any) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const t = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            const base = interimTextRef.current;
            interimTextRef.current = (base ? base + ' ' : '') + t.trim();
          } else {
            interim += t;
          }
        }
        setText(interimTextRef.current + (interim ? ' ' + interim : ''));
      };
      recognition.onerror = (err: any) => {
        console.warn('[SpeechRecognition] Error event:', err);
        setIsListening(false);
        try { recognition.abort(); } catch (_) {}
      };
      recognition.onend = () => {
        setIsListening(false);
        setText(interimTextRef.current.trim());
      };
      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.error('[SpeechRecognition] Failed to initialize mic:', err);
      setIsListening(false);
    }
  };

  // Separate attachments by type for display
  const imageAttachments = attachments.filter((a) => !!a.previewUrl);
  const nonImageAttachments = attachments.filter((a) => !a.previewUrl);

  return (
    <form onSubmit={handleSubmit} className={`space-y-3 ${className}`}>
      {/* Non-image (doc / snippet) chips — shown ABOVE the input pill */}
      {nonImageAttachments.length > 0 && (
        <div className="flex flex-wrap gap-2 animate-slide-up">
          {nonImageAttachments.map((att) => (
            <div
              key={att.id}
              className="relative group/att bg-surface border border-border-2 rounded-xl p-2 flex items-center gap-2.5 min-w-[210px] max-w-[280px] shadow-sm"
            >
              <div className="w-8 h-8 rounded-lg bg-accent/15 flex items-center justify-center text-accent flex-shrink-0">
                <FileText className="w-4 h-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-semibold text-foreground truncate">{att.file.name}</p>
                {att.isTextSnippet ? (
                  <p className="text-[9px] text-foreground-3">
                    {att.charCount?.toLocaleString()} chars · {att.wordCount} words
                  </p>
                ) : (
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <div className="flex-1 h-1 bg-surface-3 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent transition-all duration-150"
                        style={{ width: `${att.progress}%` }}
                      />
                    </div>
                    <span className="text-[8px] text-foreground-3 font-semibold">{att.progress}%</span>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {att.isTextSnippet && (
                  <>
                    <button
                      type="button"
                      onClick={() => setViewingSnippet(att)}
                      title="View file content"
                      className="p-1 rounded-md text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (att.textContent) {
                          setText((prev) => (prev ? prev + '\n' + att.textContent : att.textContent!));
                          removeAttachment(att.id);
                        }
                      }}
                      title="Unfold text back into prompt"
                      className="p-1 rounded-md text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
                    >
                      <Undo2 className="w-3.5 h-3.5" />
                    </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => removeAttachment(att.id)}
                  title="Remove attachment"
                  className="p-1 rounded-md text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Convert typed long text prompt chip */}
      {text.length > 400 && (
        <div className="flex items-center justify-between px-3 py-1.5 rounded-xl bg-accent/10 border border-accent/25 text-xs text-accent animate-fade-in">
          <div className="flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Long text prompt ({text.length.toLocaleString()} chars)</span>
          </div>
          <button
            type="button"
            onClick={() => {
              convertTextToAttachment(text);
              setText('');
            }}
            className="font-semibold underline hover:opacity-80 text-[11px]"
          >
            Convert to file attachment
          </button>
        </div>
      )}

      {/* Connected Chat Chip */}
      {connectedChat && (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#212121] text-xs text-[#F2F2F2] font-medium animate-slide-up shadow-sm w-fit">
          <div className="w-5 h-5 rounded-md bg-[#000000] flex items-center justify-center flex-shrink-0">
            <Link className="w-3 h-3 text-[#FFFFFF]" />
          </div>
          <span className="text-[#BDBDBD] text-[10.5px] font-semibold uppercase tracking-wider">Connected:</span>
          <span className="font-medium text-[#F2F2F2] truncate max-w-[200px]">{connectedChat.title}</span>
          <button
            type="button"
            onClick={() => onSelectConnectedChat?.(null)}
            className="p-0.5 rounded hover:bg-[#2B2B2B] text-[#BDBDBD] hover:text-[#F2F2F2] transition-colors ml-1"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        accept="image/*,.pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.md,.csv,.json,.py,.js,.ts,.html,.css"
        onChange={handleFileSelect}
      />

      {/* Input bar card — column layout to host inline image previews + input row */}
      <div className={`pill-input-bar pill-input-bar--col ${isLocked ? 'opacity-50 cursor-not-allowed' : ''}`}>

        {/* ── Inline image thumbnails row (inside the pill) ── */}
        {imageAttachments.length > 0 && (
          <div className="pill-image-preview-row">
            {imageAttachments.map((att) => (
              <div key={att.id} className="pill-image-thumb">
                <img
                  src={att.previewUrl}
                  alt={att.file.name}
                  className="pill-image-thumb__img"
                />
                {/* uploading spinner overlay */}
                {att.status === 'uploading' && (
                  <div className="pill-image-thumb__loading">
                    <div className="pill-image-thumb__spinner" />
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => removeAttachment(att.id)}
                  title="Remove image"
                  className="pill-image-thumb__remove"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* ── Bottom row: Plus button + textarea + mic/send ── */}
        <div className="pill-input-row">
        {/* Plus (+) Action Popover */}
        <div className="relative self-end mb-0.5" ref={plusMenuRef}>
          <button
            type="button"
            onClick={() => setShowPlusMenu((prev) => !prev)}
            disabled={isLocked}
            aria-label="Add photos, files, and skills"
            className="pill-input-side-btn"
          >
            <Plus className="w-5 h-5" strokeWidth={3} />
          </button>

          {showPlusMenu && (
            <div className="absolute bottom-full left-0 mb-2.5 z-50 w-[248px] bg-[#212121] rounded-2xl py-1.5 shadow-[0_8px_32px_rgba(0,0,0,0.65)] animate-fade-in text-[#F2F2F2] overflow-hidden">
              <button
                type="button"
                onClick={() => {
                  setShowPlusMenu(false);
                  fileInputRef.current?.click();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#2a2a2a] transition-colors text-left"
              >
                <div className="w-7 h-7 rounded-lg bg-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                  <ImageIcon className="w-[15px] h-[15px] text-[#e0e0e0]" />
                </div>
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-[#e8e8e8] leading-tight">Upload file</p>
                  <p className="text-[11px] text-[#888] leading-tight mt-0.5">Photos, docs, and more</p>
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowPlusMenu(false);
                  setToggles((prev) => ({ ...prev, webSearch: !prev.webSearch }));
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#2a2a2a] transition-colors text-left"
              >
                <div className="w-7 h-7 rounded-lg bg-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                  <Globe className="w-[15px] h-[15px] text-[#e0e0e0]" />
                </div>
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-[#e8e8e8] leading-tight">Search the web</p>
                  <p className="text-[11px] text-[#888] leading-tight mt-0.5">
                    {toggles.webSearch ? 'Enabled' : 'Find real-time info'}
                  </p>
                </div>
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowPlusMenu(false);
                  setShowConnectModal(true);
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-[#2a2a2a] transition-colors text-left"
              >
                <div className="w-7 h-7 rounded-lg bg-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                  <GitBranch className="w-[15px] h-[15px] text-[#e0e0e0]" />
                </div>
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-[#e8e8e8] leading-tight">Connect chat</p>
                  <p className="text-[11px] text-[#888] leading-tight mt-0.5">
                    {connectedChat ? `Linked: ${connectedChat.title}` : 'Reference another conversation'}
                  </p>
                </div>
              </button>

              <div className="mx-3 my-1 h-px bg-[#2B2B2B]" />

              <button
                type="button"
                onClick={() => {
                  setShowPlusMenu(false);
                  setShowAdvancedModal(true);
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-[#2a2a2a] transition-colors text-left"
              >
                <Sliders className="w-[15px] h-[15px] text-[#888] flex-shrink-0" />
                <span className="text-[13px] font-medium text-[#888]">More options</span>
              </button>
            </div>
          )}

          {/* Connect Chat Dropdown Popover */}
          {showConnectModal && (
            <div className="absolute bottom-full left-0 mb-3.5 z-50 w-72 bg-[#212121] rounded-2xl p-3 shadow-2xl space-y-2.5 animate-slide-up text-[#F2F2F2]">
              <div className="flex items-center justify-between pb-1.5">
                <div className="flex items-center gap-2">
                  <GitBranch className="w-3.5 h-3.5 text-[#FFFFFF]" />
                  <span className="font-bold text-xs text-[#F2F2F2]">Connect Chat Reference</span>
                </div>
                <button
                  type="button"
                  onClick={() => setShowConnectModal(false)}
                  className="p-1 rounded-lg text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a] transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[#8E8E8E]" />
                <input
                  type="text"
                  placeholder="Search chats to connect…"
                  value={connectSearch}
                  onChange={(e) => setConnectSearch(e.target.value)}
                  className="w-full bg-[#000000] rounded-xl pl-8 pr-2.5 py-1.5 text-xs text-[#F2F2F2] placeholder:text-[#BDBDBD] focus:outline-none transition-colors"
                />
              </div>

              <div className="max-h-44 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
                {chats.filter((c) => (c.title || 'New Chat').toLowerCase().includes(connectSearch.toLowerCase())).length === 0 ? (
                  <div className="text-center py-4 text-[11px] text-[#8E8E8E]">No conversations found</div>
                ) : (
                  chats
                    .filter((c) => (c.title || 'New Chat').toLowerCase().includes(connectSearch.toLowerCase()))
                    .map((c) => {
                      const isSelected = connectedChat?.id === c.id;
                      return (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => {
                            onSelectConnectedChat?.({ id: c.id, title: c.title || 'Untitled Chat' });
                            setShowConnectModal(false);
                          }}
                          className={`w-full flex items-center justify-between p-2 rounded-xl text-xs font-medium text-left transition-all ${
                            isSelected
                              ? 'bg-[#2F2F2F] text-[#F2F2F2] border border-[#424242]'
                              : 'hover:bg-[#2F2F2F] text-[#BDBDBD] hover:text-[#F2F2F2] border border-transparent'
                          }`}
                        >
                          <div className="flex items-center gap-2 min-w-0 flex-1">
                            <MessageSquare className="w-3.5 h-3.5 text-[#8E8E8E] flex-shrink-0" />
                            <span className="truncate text-xs">{c.title || 'New Chat'}</span>
                          </div>
                          {isSelected && (
                            <span className="text-[9px] font-bold uppercase tracking-wider text-[#FFFFFF] flex-shrink-0 ml-1">
                              Connected
                            </span>
                          )}
                        </button>
                      );
                    })
                )}
              </div>

              {connectedChat && (
                <div className="pt-1.5 border-t border-[#2B2B2B] flex justify-end">
                  <button
                    type="button"
                    onClick={() => {
                      onSelectConnectedChat?.(null);
                      setShowConnectModal(false);
                    }}
                    className="text-[11px] text-red-400 hover:text-red-300 font-medium px-2 py-1 rounded-lg hover:bg-red-900/20 transition-all"
                  >
                    Disconnect Context
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={isLocked ? 'Configure API keys to unlock…' : placeholder}
          disabled={isLocked}
          rows={1}
          className="flex-1 bg-transparent resize-none text-base font-medium text-foreground placeholder:text-foreground-3/80 focus:outline-none leading-relaxed disabled:cursor-not-allowed py-1 custom-scrollbar"
          style={{ maxHeight: '180px', minHeight: '24px' }}
          aria-label="Message input"
        />

        <div className="flex items-center gap-1 flex-shrink-0 self-end mb-0.5">
          {!isStreaming && enableDictation && (
            <div
              className={`mic-tooltip-wrap${isListening ? ' mic-listening' : ''}`}
              data-tip={!voiceSupported ? 'Not supported' : isListening ? 'Click to stop' : 'Click to speak'}
            >
              <button
                type="button"
                onClick={handleToggleMic}
                aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
                disabled={isLocked || !voiceSupported}
                className={`pill-input-side-btn transition-colors duration-150 ${
                  isListening ? 'text-red-400' : ''
                } ${!voiceSupported ? 'opacity-30 cursor-not-allowed' : ''}`}
              >
                <Mic className={`w-4 h-4 ${isListening ? 'animate-pulse' : ''}`} strokeWidth={2.6} />
              </button>
            </div>
          )}

          {isStreaming ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generation"
              className="pill-send-btn"
            >
              <Square className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={(!text.trim() && attachments.length === 0) || isLocked}
              aria-label={isLocked ? 'Chat is locked' : 'Send'}
              className="pill-send-btn"
            >
              <ArrowUp className="w-4 h-4" strokeWidth={2.5} />
            </button>
          )}
        </div>
        </div>{/* end pill-input-row */}
      </div>

      <div className="flex items-center justify-center text-[11px] text-[#808080] px-1 pt-1.5 font-normal tracking-wide">
        <span>openChat can make mistakes. Check important info.</span>
      </div>

      {/* Snippet Viewer Modal */}
      {viewingSnippet && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 animate-fade-in">
          <div className="bg-[#212121] border border-[#2F2F2F] rounded-2xl max-w-3xl w-full p-6 space-y-4 shadow-2xl text-[#F2F2F2]">
            <div className="flex items-center justify-between border-b border-[#2F2F2F] pb-3.5">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-[#212121] border border-[#2B2B2B]">
                  <FileText className="w-4 h-4 text-[#FFFFFF]" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm text-[#F2F2F2]">{viewingSnippet.file.name}</h3>
                  <p className="text-[11px] text-[#BDBDBD] font-mono">
                    {viewingSnippet.charCount?.toLocaleString()} chars &middot; {viewingSnippet.wordCount?.toLocaleString()} words
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setViewingSnippet(null)}
                className="p-1.5 rounded-xl text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2F2F2F] transition-all"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <textarea
              value={viewingSnippet.textContent || ''}
              onChange={(e) => {
                const val = e.target.value;
                setAttachments((prev) =>
                  prev.map((a) =>
                    a.id === viewingSnippet.id
                      ? {
                          ...a,
                          textContent: val,
                          charCount: val.length,
                          wordCount: val.trim().split(/\s+/).filter(Boolean).length,
                        }
                      : a
                  )
                );
                setViewingSnippet((prev) => (prev ? { ...prev, textContent: val, charCount: val.length } : null));
              }}
              rows={14}
              className="w-full rounded-xl bg-[#000000] p-4 text-xs font-mono text-[#F2F2F2] border border-[#2B2B2B] focus:outline-none focus:border-[#444] resize-y custom-scrollbar leading-relaxed"
            />
            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-[#8E8E8E]">Editable preview snippet</span>
              <button
                type="button"
                onClick={() => setViewingSnippet(null)}
                className="px-5 py-2 rounded-xl bg-[#FFFFFF] text-[#000000] hover:bg-[#E5E5E5] text-xs font-bold transition-all active:scale-[0.97] shadow-md"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Advanced Capabilities Toggle Modal */}
      <AdvancedTogglesModal
        isOpen={showAdvancedModal}
        onClose={() => setShowAdvancedModal(false)}
        toggles={toggles}
        onToggleChange={(key, value) =>
          setToggles((prev) => ({ ...prev, [key]: value }))
        }
      />
    </form>
  );
});
