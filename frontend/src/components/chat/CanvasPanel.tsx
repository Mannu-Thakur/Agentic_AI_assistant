import React, { useState, useRef, useEffect, useCallback } from 'react';
import { apiRequest } from '../../services/api';
import {
  Pencil, Copy, Download, Maximize2, Minimize2, X,
  Bold, Italic, Link2, ChevronDown, Check, MessageSquarePlus,
  Heading1, Heading2, Heading3, AlignLeft,
} from 'lucide-react';

/* ── Types ── */
interface CanvasPanelProps {
  isOpen: boolean;
  content: string;
  messageId: string;
  onClose: () => void;
  onApplyChanges: (newContent: string) => void;
}

/* ── Format options dropdown ── */
const FORMAT_OPTIONS = [
  { label: 'Paragraph',   icon: AlignLeft,  tag: '' },
  { label: 'Heading 1',   icon: Heading1,   tag: '# ' },
  { label: 'Heading 2',   icon: Heading2,   tag: '## ' },
  { label: 'Heading 3',   icon: Heading3,   tag: '### ' },
];

/* ── Small toolbar icon button ── */
const ToolBtn: React.FC<{
  onClick: () => void;
  title: string;
  active?: boolean;
  children: React.ReactNode;
}> = ({ onClick, title, active, children }) => (
  <button
    type="button"
    onClick={onClick}
    title={title}
    className={`p-1.5 rounded-md text-[13px] font-medium transition-colors ${
      active
        ? 'bg-[#F2F2F2] text-[#000000]'
        : 'text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a]'
    }`}
  >
    {children}
  </button>
);

/* ══════════════════════════════════════════════
   Main component
   ══════════════════════════════════════════════ */
export const CanvasPanel: React.FC<CanvasPanelProps> = ({
  isOpen,
  content,
  messageId,
  onClose,
  onApplyChanges,
}) => {
  const [text, setText]                   = useState(content);
  const [copied, setCopied]               = useState(false);
  const [expanded, setExpanded]           = useState(false);
  const [showFormatMenu, setShowFormatMenu] = useState(false);
  const [activeFormat, setActiveFormat]   = useState('Paragraph');

  /* "Ask for changes" bar */
  const [showAskBar, setShowAskBar]       = useState(false);
  const [askQuery, setAskQuery]           = useState('');

  /* Link dialog */
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const [linkUrl, setLinkUrl]             = useState('');
  const [savedRange, setSavedRange]       = useState<{ start: number; end: number } | null>(null);

  const textareaRef   = useRef<HTMLTextAreaElement>(null);
  const formatMenuRef = useRef<HTMLDivElement>(null);
  const linkInputRef  = useRef<HTMLInputElement>(null);
  const askInputRef   = useRef<HTMLInputElement>(null);

  const [isUserEditing, setIsUserEditing] = useState(false);

  /* sync content when prop changes if user is not actively editing */
  useEffect(() => {
    if (!isUserEditing) {
      setText(content);
    }
  }, [content, messageId, isUserEditing]);

  /* auto-resize textarea */
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${ta.scrollHeight}px`;
  }, [text]);

  /* close format menu on outside click */
  useEffect(() => {
    if (!showFormatMenu) return;
    const handler = (e: MouseEvent) => {
      if (formatMenuRef.current && !formatMenuRef.current.contains(e.target as Node))
        setShowFormatMenu(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showFormatMenu]);

  /* focus ask input when shown */
  useEffect(() => { if (showAskBar) askInputRef.current?.focus(); }, [showAskBar]);
  useEffect(() => { if (showLinkDialog) linkInputRef.current?.focus(); }, [showLinkDialog]);

  /* ── Helpers ── */
  const getSelection = () => {
    const ta = textareaRef.current;
    if (!ta) return null;
    return { start: ta.selectionStart, end: ta.selectionEnd };
  };

  const wrapSelection = useCallback((prefix: string, suffix: string) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const { start, end } = getSelection() ?? { start: 0, end: 0 };
    const selected = text.slice(start, end);
    const newText  = text.slice(0, start) + prefix + selected + suffix + text.slice(end);
    setText(newText);
    setTimeout(() => {
      ta.selectionStart = start + prefix.length;
      ta.selectionEnd   = end + prefix.length;
      ta.focus();
    }, 0);
  }, [text]);

  const handleBold   = () => wrapSelection('**', '**');
  const handleItalic = () => wrapSelection('*', '*');

  const handleLink = () => {
    const sel = getSelection();
    if (sel) setSavedRange(sel);
    setShowLinkDialog(true);
  };

  const applyLink = () => {
    if (!savedRange || !linkUrl.trim()) { setShowLinkDialog(false); return; }
    const { start, end } = savedRange;
    const selected = text.slice(start, end) || linkUrl;
    const newText  = text.slice(0, start) + `[${selected}](${linkUrl})` + text.slice(end);
    setText(newText);
    setShowLinkDialog(false);
    setLinkUrl('');
    textareaRef.current?.focus();
  };

  const applyFormat = (tag: string, label: string) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const pos   = ta.selectionStart;
    const lines = text.split('\n');
    let chars   = 0;
    let lineIdx = 0;
    for (let i = 0; i < lines.length; i++) {
      chars += lines[i].length + 1;
      if (chars > pos) { lineIdx = i; break; }
    }
    const stripped  = lines[lineIdx].replace(/^#+\s/, '');
    lines[lineIdx]  = tag + stripped;
    setText(lines.join('\n'));
    setActiveFormat(label);
    setShowFormatMenu(false);
    ta.focus();
  };

  const copyTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([text], { type: 'text/markdown' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'response.md'; a.click();
    URL.revokeObjectURL(url);
  };

  const handleAsk = async () => {
    if (!askQuery.trim()) return;
    const promptText = `Refine the following text according to this instruction: "${askQuery}". Text:\n\n${text}`;
    setAskQuery('');
    setShowAskBar(false);
    try {
      const res = await apiRequest<{ response?: string }>('/api/v1/chat', {
        method: 'POST',
        body: JSON.stringify({ message: promptText, stream: false }),
      });
      if (res && res.response) {
        setText(res.response);
      }
    } catch (err) {
      console.error('Failed to transform canvas text via AI:', err);
    }
  };

  if (!isOpen) return null;

  const panelHeight = expanded ? 'h-[70vh]' : 'max-h-[420px]';

  return (
    <div
      className={`w-full bg-[#212121] rounded-2xl overflow-hidden shadow-[0_8px_40px_rgba(0,0,0,0.5)] flex flex-col animate-fade-in-up mt-3 transition-all duration-300 ${panelHeight}`}
    >
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-2.5 flex-shrink-0">
        {/* Left: label */}
        <div className="flex items-center gap-2">
          <Pencil className="w-3.5 h-3.5 text-[#BDBDBD]" />
          <span className="text-[13px] font-semibold text-[#F2F2F2]">Edit</span>
          <span className="text-[10px] text-[#808080] bg-[#2a2a2a] px-1.5 py-0.5 rounded-md font-mono">
            {text.length} chars
          </span>
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-1">
          <ToolBtn onClick={handleCopy} title="Copy to clipboard">
            {copied ? <Check className="w-3.5 h-3.5 text-[#F2F2F2]" /> : <Copy className="w-3.5 h-3.5" />}
          </ToolBtn>
          <ToolBtn onClick={handleDownload} title="Download as Markdown">
            <Download className="w-3.5 h-3.5" />
          </ToolBtn>
          <ToolBtn onClick={() => setExpanded(e => !e)} title={expanded ? 'Collapse' : 'Expand'}>
            {expanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </ToolBtn>
          <div className="w-px h-4 bg-[#2B2B2B] mx-1" />
          <ToolBtn onClick={onClose} title="Close">
            <X className="w-3.5 h-3.5" />
          </ToolBtn>
        </div>
      </div>

      {/* ── Toolbar ── */}
      <div className="flex items-center gap-0.5 px-3 py-2 flex-shrink-0 flex-wrap">
        {/* Ask for changes */}
        <button
          type="button"
          onClick={() => setShowAskBar(v => !v)}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12px] font-medium transition-colors ${
            showAskBar
              ? 'bg-[#F2F2F2] text-[#000000]'
              : 'text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a]'
          }`}
        >
          <MessageSquarePlus className="w-3.5 h-3.5" />
          <span>Ask for changes</span>
          <kbd className="ml-0.5 text-[9px] bg-[#2a2a2a] px-1 py-0.5 rounded font-mono text-[#808080]">
            Ctrl+K
          </kbd>
        </button>

        <div className="w-px h-4 bg-[#2B2B2B] mx-1.5" />

        {/* Link */}
        <ToolBtn onClick={handleLink} title="Insert link">
          <Link2 className="w-3.5 h-3.5" />
        </ToolBtn>

        {/* Bold */}
        <ToolBtn onClick={handleBold} title="Bold (wrap with **)">
          <Bold className="w-3.5 h-3.5" />
        </ToolBtn>

        {/* Italic */}
        <ToolBtn onClick={handleItalic} title="Italic (wrap with *)">
          <Italic className="w-3.5 h-3.5" />
        </ToolBtn>

        <div className="w-px h-4 bg-[#2B2B2B] mx-1.5" />

        {/* Format dropdown */}
        <div className="relative" ref={formatMenuRef}>
          <button
            type="button"
            onClick={() => setShowFormatMenu(v => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12px] font-medium text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a] transition-colors"
          >
            <span>{activeFormat}</span>
            <ChevronDown className="w-3 h-3" />
          </button>

          {showFormatMenu && (
            <div className="absolute top-full left-0 mt-1 z-50 w-40 bg-[#212121] rounded-xl shadow-[0_8px_24px_rgba(0,0,0,0.6)] overflow-hidden animate-fade-in">
              {FORMAT_OPTIONS.map(({ label, icon: Icon, tag }) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => applyFormat(tag, label)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 text-[12px] transition-colors text-left ${
                    activeFormat === label
                      ? 'bg-[#2a2a2a] text-[#F2F2F2]'
                      : 'text-[#BDBDBD] hover:bg-[#2a2a2a] hover:text-[#F2F2F2]'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                  {label}
                  {activeFormat === label && <Check className="w-3 h-3 ml-auto" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Apply button */}
        <button
          type="button"
          onClick={() => { onApplyChanges(text); onClose(); }}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold bg-[#F2F2F2] text-[#000000] hover:bg-[#E8E8E8] transition-colors"
        >
          <Check className="w-3.5 h-3.5" />
          Apply
        </button>
      </div>

      {/* ── Ask for changes bar ── */}
      {showAskBar && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-[#000000]/30 flex-shrink-0 animate-fade-in">
          <MessageSquarePlus className="w-3.5 h-3.5 text-[#BDBDBD] flex-shrink-0" />
          <input
            ref={askInputRef}
            value={askQuery}
            onChange={e => setAskQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') handleAsk();
              if (e.key === 'Escape') { setShowAskBar(false); setAskQuery(''); }
            }}
            placeholder='e.g. "make it shorter", "add bullet points", "make it formal"'
            className="flex-1 bg-transparent text-[13px] text-[#F2F2F2] placeholder:text-[#808080] focus:outline-none"
          />
          <button
            type="button"
            onClick={handleAsk}
            disabled={!askQuery.trim()}
            className="px-3 py-1 rounded-lg text-[11px] font-semibold bg-[#F2F2F2] text-[#000000] hover:bg-[#E8E8E8] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Apply
          </button>
        </div>
      )}

      {/* ── Link dialog ── */}
      {showLinkDialog && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-[#000000]/30 flex-shrink-0 animate-fade-in">
          <Link2 className="w-3.5 h-3.5 text-[#BDBDBD] flex-shrink-0" />
          <input
            ref={linkInputRef}
            value={linkUrl}
            onChange={e => setLinkUrl(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') applyLink();
              if (e.key === 'Escape') { setShowLinkDialog(false); setLinkUrl(''); }
            }}
            placeholder="Paste URL and press Enter"
            className="flex-1 bg-transparent text-[13px] text-[#F2F2F2] placeholder:text-[#808080] focus:outline-none"
          />
          <button type="button" onClick={applyLink} className="px-3 py-1 rounded-lg text-[11px] font-semibold bg-[#F2F2F2] text-[#000000] hover:bg-[#E8E8E8] transition-colors">
            Insert
          </button>
          <button type="button" onClick={() => { setShowLinkDialog(false); setLinkUrl(''); }} className="p-1 text-[#BDBDBD] hover:text-[#F2F2F2] transition-colors">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ── Editable content ── */}
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-4">
        <textarea
          ref={textareaRef}
          value={text}
          onFocus={() => setIsUserEditing(true)}
          onChange={e => { setText(e.target.value); setIsUserEditing(true); }}
          onKeyDown={e => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
              e.preventDefault();
              setShowAskBar(v => !v);
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
              e.preventDefault();
              handleBold();
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
              e.preventDefault();
              handleItalic();
            }
          }}
          spellCheck
          className="w-full bg-transparent text-[14px] text-[#F2F2F2] leading-[1.75] font-['Inter',sans-serif] resize-none focus:outline-none placeholder:text-[#808080] selection:bg-[rgba(255,255,255,0.15)]"
          style={{ minHeight: 120 }}
          placeholder="Start writing or paste text here…"
        />
      </div>

      {/* ── Footer hint ── */}
      <div className="px-4 py-2 flex items-center gap-4 text-[10px] text-[#808080] flex-shrink-0">
        <span><kbd className="font-mono bg-[#2a2a2a] px-1 rounded">Ctrl+B</kbd> Bold</span>
        <span><kbd className="font-mono bg-[#2a2a2a] px-1 rounded">Ctrl+I</kbd> Italic</span>
        <span><kbd className="font-mono bg-[#2a2a2a] px-1 rounded">Ctrl+K</kbd> Ask for changes</span>
        <span className="ml-auto">Markdown supported</span>
      </div>
    </div>
  );
};
