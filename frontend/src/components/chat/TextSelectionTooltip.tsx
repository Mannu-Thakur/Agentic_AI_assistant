import React, { useState, useEffect } from 'react';
import { Sparkles, Edit3 } from 'lucide-react';

interface TextSelectionTooltipProps {
  containerRef: React.RefObject<HTMLElement | null>;
  onAsk: (selectedText: string) => void;
  onStartWriting: (selectedText: string) => void;
}

export const TextSelectionTooltip: React.FC<TextSelectionTooltipProps> = ({
  containerRef,
  onAsk,
  onStartWriting,
}) => {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const [selectedText, setSelectedText] = useState('');

  useEffect(() => {
    const handleSelection = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.toString().trim()) {
        setPosition(null);
        setSelectedText('');
        return;
      }

      const text = selection.toString().trim();
      if (text.length < 3) {
        setPosition(null);
        return;
      }

      if (containerRef.current && containerRef.current.contains(selection.anchorNode)) {
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        setSelectedText(text);
        setPosition({
          top: rect.top - 50,
          left: rect.left + rect.width / 2,
        });
      } else {
        setPosition(null);
      }
    };

    document.addEventListener('selectionchange', handleSelection);
    return () => document.removeEventListener('selectionchange', handleSelection);
  }, [containerRef]);

  if (!position || !selectedText) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: `${Math.max(8, position.top)}px`,
        left: `${position.left}px`,
        transform: 'translateX(-50%)',
      }}
      className="z-50 flex items-center gap-1 p-1 bg-[#212121] border border-[#2B2B2B] rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.6)] animate-fade-in"
    >
      <button
        onClick={() => { onAsk(selectedText); setPosition(null); }}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold text-[#000000] bg-[#FFFFFF] hover:bg-[#E8E8E8] transition-colors"
      >
        <Sparkles className="w-3 h-3" />
        <span>Ask</span>
      </button>

      <button
        onClick={() => { onStartWriting(selectedText); setPosition(null); }}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold text-[#BDBDBD] hover:text-[#F2F2F2] bg-[#2a2a2a] hover:bg-[#333] border border-[#2B2B2B] transition-colors"
      >
        <Edit3 className="w-3 h-3" />
        <span>Write</span>
      </button>
    </div>
  );
};
