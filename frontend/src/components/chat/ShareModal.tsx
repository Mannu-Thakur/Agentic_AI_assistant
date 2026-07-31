import React, { useState } from 'react';
import { X as CloseIcon, Copy, Check, Bot } from 'lucide-react';

interface ShareModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  content: string;
  shareUrl?: string;
}

export const ShareModal: React.FC<ShareModalProps> = ({
  isOpen,
  onClose,
  title = 'Shared Conversation',
  content,
  shareUrl,
}) => {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const currentUrl = shareUrl || (typeof window !== 'undefined' ? window.location.href : '');
  const encodedUrl = encodeURIComponent(currentUrl);
  const encodedText = encodeURIComponent(`Check out this response from openChat:\n"${content.slice(0, 120)}..."`);

  const handleCopyLink = () => {
    navigator.clipboard.writeText(currentUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const socialLinks = [
    {
      name: 'Copy link',
      icon: copied ? Check : Copy,
      onClick: handleCopyLink,
      isCopied: copied,
    },
    {
      name: 'X / Twitter',
      icon: (props: any) => (
        <svg viewBox="0 0 24 24" className="w-5 h-5 fill-current" {...props}>
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
      ),
      url: `https://twitter.com/intent/tweet?url=${encodedUrl}&text=${encodedText}`,
    },
    {
      name: 'LinkedIn',
      icon: (props: any) => (
        <svg viewBox="0 0 24 24" className="w-5 h-5 fill-current" {...props}>
          <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z" />
        </svg>
      ),
      url: `https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`,
    },
    {
      name: 'Reddit',
      icon: (props: any) => (
        <svg viewBox="0 0 24 24" className="w-5 h-5 fill-current" {...props}>
          <path d="M12 2A10 10 0 0 0 2 12a10 10 0 0 0 10 10 10 10 0 0 0 10-10A10 10 0 0 0 12 2zm5.01 4.75c.68 0 1.29.43 1.54 1.06a1.63 1.63 0 0 1-.36 1.74c-.05.06-.11.13-.17.19.03.22.05.45.05.69 0 3.53-4.04 6.39-9.04 6.39s-9.04-2.86-9.04-6.39c0-.24.02-.47.05-.69a1.59 1.59 0 0 1-.53-1.93 1.64 1.64 0 0 1 1.54-1.06c.46 0 .88.2 1.18.52 1.43-1 3.39-1.65 5.56-1.73l1.17-3.69a.37.37 0 0 1 .45-.24l3.19.75c.2-.35.58-.59 1.02-.59a1.21 1.21 0 1 1-1.21 1.21c0-.05.01-.1.02-.15l-2.86-.67-.98 3.12c2.14.09 4.08.73 5.51 1.73.3-.32.72-.52 1.18-.52zM9.25 12C8.56 12 8 12.56 8 13.25S8.56 14.5 9.25 14.5 10.5 13.94 10.5 13.25 9.94 12 9.25 12zm5.5 0c-.69 0-1.25.56-1.25 1.25s.56 1.25 1.25 1.25 1.25-.56 1.25-1.25-.56-1.25-1.25-1.25zm-5.46 4.38a.38.38 0 0 0-.27.65c.9.9 2.37 1.22 3.73 1.22s2.83-.32 3.73-1.22a.38.38 0 1 0-.53-.53c-.76.76-2.03 1.02-3.2 1.02s-2.44-.26-3.2-1.02a.37.37 0 0 0-.26-.12z" />
        </svg>
      ),
      url: `https://reddit.com/submit?url=${encodedUrl}&title=${encodedText}`,
    },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative w-full max-w-md bg-[#212121] border border-[#2B2B2B] rounded-2xl shadow-[0_16px_48px_rgba(0,0,0,0.7)] overflow-hidden text-[#F2F2F2]">

        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4">
          <h2 className="text-[15px] font-semibold text-[#F2F2F2]">{title}</h2>
          <button
            onClick={onClose}
            className="p-1 text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a] rounded-lg transition-colors"
          >
            <CloseIcon className="w-4 h-4" />
          </button>
        </div>

        <div className="mx-5 h-px bg-[#2B2B2B]" />

        {/* Content Preview */}
        <div className="mx-5 my-4 bg-[#000000] border border-[#2B2B2B] rounded-xl p-4 overflow-hidden">
          <div className="max-h-36 overflow-y-auto custom-scrollbar">
            <p className="text-[13px] text-[#F2F2F2] leading-relaxed line-clamp-6">{content.slice(0, 400)}{content.length > 400 ? '…' : ''}</p>
          </div>
          <div className="mt-3 pt-3 border-t border-[#2B2B2B] flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-[#FFFFFF]">
              <Bot className="w-3 h-3" />
              <span>openChat AI</span>
            </div>
            <span className="text-[10px] text-[#BDBDBD]">Preview</span>
          </div>
        </div>

        {/* Share actions */}
        <div className="flex items-center justify-around gap-2 px-5 pb-5">
          {socialLinks.map((item) => {
            const Icon = item.icon;
            const base = "flex flex-col items-center gap-1.5 group focus:outline-none";
            const circle = "w-12 h-12 rounded-full bg-[#2a2a2a] border border-[#2B2B2B] text-[#FFFFFF] flex items-center justify-center transition-all group-hover:bg-[#333] group-hover:border-[#444] group-hover:scale-105";

            if (item.onClick) {
              return (
                <button key={item.name} onClick={item.onClick} className={base}>
                  <div className={circle}><Icon className="w-5 h-5" /></div>
                  <span className="text-[11px] text-[#BDBDBD] group-hover:text-[#F2F2F2]">
                    {item.isCopied ? 'Copied!' : item.name}
                  </span>
                </button>
              );
            }
            return (
              <a key={item.name} href={item.url} target="_blank" rel="noopener noreferrer" className={base}>
                <div className={circle}><Icon className="w-5 h-5" /></div>
                <span className="text-[11px] text-[#BDBDBD] group-hover:text-[#F2F2F2]">{item.name}</span>
              </a>
            );
          })}
        </div>
      </div>
    </div>
  );
};
