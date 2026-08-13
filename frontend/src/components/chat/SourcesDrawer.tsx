import React, { useState } from 'react';
import { X, Globe, FileText, ChevronDown, ChevronRight, CheckCircle2, Clock, Sparkles, ExternalLink } from 'lucide-react';

export interface SourceItem {
  id: string;
  title: string;
  url?: string;
  domain?: string;
  snippet?: string;
  score?: number;
  type?: 'web' | 'document' | 'tool';
}

export interface ActivityTrace {
  executionTimeSeconds?: number;
  thinkingProcess?: string[];
  queries?: string[];
  domainChips?: string[];
  toolsUsed?: string[];
}

interface SourcesDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  sources?: SourceItem[];
  activity?: ActivityTrace;
}

export const SourcesDrawer: React.FC<SourcesDrawerProps> = ({
  isOpen,
  onClose,
  sources = [],
  activity,
}) => {
  const [thinkingExpanded, setThinkingExpanded] = useState(true);

  const executionTime = activity?.executionTimeSeconds || 1.2;
  const domainChips = activity?.domainChips || sources.map(s => s.domain).filter(Boolean) as string[];
  const thinkingSteps = activity?.thinkingProcess || [
    'Analyzed prompt intent & scope',
    'Consulted internal knowledge & document retriever',
    'Synthesized precise response',
  ];

  /* ── Inline side-panel — animates width so chat stays scrollable ── */
  return (
    <div
      className="flex-shrink-0 flex flex-col bg-[#0a0a0a] text-[#F2F2F2] transition-all duration-300 ease-in-out overflow-hidden"
      style={{
        width: isOpen ? 340 : 0,
        opacity: isOpen ? 1 : 0,
        pointerEvents: isOpen ? 'auto' : 'none',
      }}
      aria-hidden={!isOpen}
    >
      {/* inner wrapper keeps content from reflowing during width animation */}
      <div className="w-[340px] flex flex-col h-full">

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3.5 flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <h3 className="text-[13px] font-semibold text-[#F2F2F2]">Activity</h3>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#212121] text-[11px] font-medium text-[#BDBDBD]">
              <Clock className="w-2.5 h-2.5" />
              {executionTime}s
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a] rounded-lg transition-colors"
            aria-label="Close sources panel"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-4 space-y-4 min-h-0">

          {/* Thinking Accordion */}
          <div className="bg-[#141414] rounded-xl overflow-hidden">
            <button
              onClick={() => setThinkingExpanded(!thinkingExpanded)}
              className="w-full px-3.5 py-3 flex items-center justify-between hover:bg-[#1a1a1a] transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                <Sparkles className="w-3.5 h-3.5 text-[#FFFFFF]" />
                <span className="text-[12px] font-semibold text-[#F2F2F2]">Thinking process</span>
              </div>
              {thinkingExpanded
                ? <ChevronDown className="w-3.5 h-3.5 text-[#BDBDBD]" />
                : <ChevronRight className="w-3.5 h-3.5 text-[#BDBDBD]" />}
            </button>

            {thinkingExpanded && (
              <div className="px-3.5 pb-3.5 space-y-2 pt-2">
                {thinkingSteps.map((step, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <CheckCircle2 className="w-3 h-3 text-[#FFFFFF] mt-0.5 flex-shrink-0" />
                    <span className="text-[11px] text-[#BDBDBD] leading-relaxed">{step}</span>
                  </div>
                ))}

                {domainChips.length > 0 && (
                  <div className="pt-2 flex flex-wrap gap-1.5">
                    {domainChips.map((domain, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-[#212121] text-[10px] text-[#BDBDBD]"
                      >
                        <Globe className="w-2.5 h-2.5 text-[#FFFFFF]" />
                        {domain}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Sources & Citations */}
          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#BDBDBD] px-0.5">
              Sources &amp; Citations
            </p>

            {sources.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 bg-[#141414] rounded-xl gap-2">
                <Globe className="w-6 h-6 text-[#BDBDBD] opacity-30" />
                <p className="text-[11px] text-[#808080]">No additional sources found</p>
              </div>
            ) : (
              <div className="space-y-2">
                {sources.map((item) => (
                  <div
                    key={item.id}
                    className="p-3 bg-[#141414] hover:bg-[#1f1f1f] rounded-xl transition-colors group"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {item.type === 'document'
                          ? <FileText className="w-3 h-3 text-[#FFFFFF] flex-shrink-0" />
                          : <Globe className="w-3 h-3 text-[#FFFFFF] flex-shrink-0" />}
                        <span className="text-[12px] font-medium text-[#F2F2F2] truncate">{item.title}</span>
                      </div>
                      {item.url && (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[#BDBDBD] hover:text-[#FFFFFF] flex-shrink-0 transition-colors"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>

                    {item.snippet && (
                      <p className="text-[11px] text-[#BDBDBD] line-clamp-2 leading-relaxed">{item.snippet}</p>
                    )}

                    {item.domain && (
                      <p className="text-[10px] text-[#808080] mt-1">{item.domain}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
