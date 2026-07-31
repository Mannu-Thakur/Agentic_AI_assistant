import React from 'react';
import { X, Search, Volume2, Database } from 'lucide-react';

interface FeatureToggles {
  webSearch: boolean;
  canvas: boolean;
  voice: boolean;
  connectorSearch: boolean;
}

interface AdvancedTogglesModalProps {
  isOpen: boolean;
  onClose: () => void;
  toggles: FeatureToggles;
  onToggleChange: (key: keyof FeatureToggles, value: boolean) => void;
}

export const AdvancedTogglesModal: React.FC<AdvancedTogglesModalProps> = ({
  isOpen,
  onClose,
  toggles,
  onToggleChange,
}) => {
  if (!isOpen) return null;

  const features = [
    {
      key: 'webSearch' as keyof FeatureToggles,
      title: 'Web search',
      description: 'Search the web automatically for up-to-date answers.',
      icon: Search,
    },
    {
      key: 'voice' as keyof FeatureToggles,
      title: 'Voice & Speech',
      description: 'Voice dictation input and text-to-speech readback.',
      icon: Volume2,
    },
    {
      key: 'connectorSearch' as keyof FeatureToggles,
      title: 'Connector search',
      description: 'Search workspace files, vector stores, and linked sources.',
      icon: Database,
    },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="relative w-full max-w-sm bg-[#1a1a1a] border border-[#303030] rounded-2xl shadow-[0_16px_48px_rgba(0,0,0,0.6)] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3">
          <h3 className="text-[15px] font-semibold text-[#e8e8e8]">Advanced</h3>
          <button
            onClick={onClose}
            className="p-1 text-[#888] hover:text-[#e0e0e0] hover:bg-[#2a2a2a] rounded-lg transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Divider */}
        <div className="mx-5 h-px bg-[#303030]" />

        {/* Features */}
        <div className="px-3 py-2">
          {features.map((item) => {
            const Icon = item.icon;
            const isChecked = toggles[item.key];

            return (
              <label
                key={item.key}
                className="flex items-center justify-between gap-3 px-2 py-3 rounded-xl hover:bg-[#222] transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-7 h-7 rounded-lg bg-[#2a2a2a] flex items-center justify-center flex-shrink-0">
                    <Icon className="w-[15px] h-[15px] text-[#999]" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium text-[#e0e0e0] leading-tight">{item.title}</p>
                    <p className="text-[11px] text-[#777] leading-tight mt-0.5">{item.description}</p>
                  </div>
                </div>

                {/* Toggle switch */}
                <div className="relative flex-shrink-0">
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={(e) => onToggleChange(item.key, e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-[#252528] border border-[#38383c] rounded-full peer peer-checked:bg-blue-600 peer-checked:border-blue-600 transition-colors duration-200 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[#888] after:rounded-full after:h-4 after:w-4 after:transition-all after:duration-200 peer-checked:after:translate-x-4 peer-checked:after:bg-white" />
                </div>
              </label>
            );
          })}
        </div>
      </div>
    </div>
  );
};
