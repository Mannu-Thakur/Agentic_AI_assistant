import React, { useState, useEffect, useRef } from 'react';
import { Volume2, VolumeX, BookOpen, GitBranch, Share2, MoreHorizontal } from 'lucide-react';
import { Tooltip } from '../ui/Tooltip';

interface AnswerContextMenuProps {
  createdAt?: string;
  content: string;
  onOpenSources?: () => void;
  onBranch?: () => void;
  onShare?: () => void;
}

export const AnswerContextMenu: React.FC<AnswerContextMenuProps> = ({
  createdAt,
  content,
  onOpenSources,
  onBranch,
  onShare,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [openUpward, setOpenUpward] = useState(true);
  const menuRef = useRef<HTMLDivElement>(null);

  const formatTimestamp = (dateStr?: string) => {
    if (!dateStr) return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    try {
      let s = dateStr.trim();
      if (!s.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(s)) {
        s = s.replace(' ', 'T');
        if (!s.includes('T')) s += 'T00:00:00Z';
        else s += 'Z';
      }
      const d = new Date(s);
      const isToday = new Date().toDateString() === d.toDateString();
      const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return isToday ? timeStr : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${timeStr}`;
    } catch { return ''; }
  };

  const handleReadAloud = () => {
    if (!('speechSynthesis' in window)) return;
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    } else {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(content.replace(/[*#`_]/g, ''));
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);
      setIsSpeaking(true);
      window.speechSynthesis.speak(utterance);
    }
    setIsOpen(false);
  };

  const handleOpen = () => {
    if (!menuRef.current) { setIsOpen(true); return; }
    const rect = menuRef.current.getBoundingClientRect();
    setOpenUpward(rect.top >= 220);
    setIsOpen(true);
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const menuItemCls = "w-full flex items-center gap-2.5 px-3 py-2 text-[12px] font-medium text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a] rounded-lg transition-colors text-left";

  return (
    <div className="relative inline-block" ref={menuRef}>
      <Tooltip content="More actions" side="top">
        <button
          onClick={() => isOpen ? setIsOpen(false) : handleOpen()}
          className="p-1 text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a] rounded-lg transition-colors"
          aria-label="More actions"
        >
          <MoreHorizontal className="w-3.5 h-3.5" />
        </button>
      </Tooltip>

      {isOpen && (
        <div className={`absolute left-0 z-50 w-48 bg-[#212121] border border-[#2B2B2B] rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.6)] overflow-hidden animate-fade-in p-1 ${
          openUpward ? 'bottom-full mb-1.5' : 'top-full mt-1.5'
        }`}>
          {/* Timestamp */}
          <div className="px-3 py-1.5 text-[10px] text-[#808080] border-b border-[#2B2B2B] mb-0.5 font-medium">
            {formatTimestamp(createdAt)}
          </div>

          <div className="space-y-0.5 pt-0.5">
            {onOpenSources && (
              <button onClick={() => { setIsOpen(false); onOpenSources(); }} className={menuItemCls}>
                <BookOpen className="w-3.5 h-3.5 text-[#FFFFFF] flex-shrink-0" />
                View sources
              </button>
            )}

            {onBranch && (
              <button onClick={() => { setIsOpen(false); onBranch(); }} className={menuItemCls}>
                <GitBranch className="w-3.5 h-3.5 text-[#FFFFFF] flex-shrink-0" />
                Branch in new chat
              </button>
            )}

            <button onClick={handleReadAloud} className={menuItemCls}>
              {isSpeaking
                ? <><VolumeX className="w-3.5 h-3.5 text-[#FFFFFF] flex-shrink-0" />Stop reading</>
                : <><Volume2 className="w-3.5 h-3.5 text-[#FFFFFF] flex-shrink-0" />Read aloud</>}
            </button>

            {onShare && (
              <button onClick={() => { setIsOpen(false); onShare(); }} className={menuItemCls}>
                <Share2 className="w-3.5 h-3.5 text-[#FFFFFF] flex-shrink-0" />
                Share answer
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
