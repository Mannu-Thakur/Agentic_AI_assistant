import { useEffect } from 'react';
import { X, Command } from 'lucide-react';

interface ShortcutGroup {
  category: string;
  shortcuts: { keys: string[]; description: string }[];
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    category: 'Navigation',
    shortcuts: [
      { keys: ['Ctrl', 'N'], description: 'New Chat' },
      { keys: ['Ctrl', 'K'], description: 'Global Search' },
      { keys: ['Ctrl', '/'], description: 'Show Keyboard Shortcuts' },
      { keys: ['Esc'], description: 'Close Modal / Drawer' },
    ],
  },
  {
    category: 'Messaging',
    shortcuts: [
      { keys: ['Enter'], description: 'Send Message' },
      { keys: ['Shift', 'Enter'], description: 'New Line in Input' },
    ],
  },
];

interface KeyboardShortcutsModalProps {
  open: boolean;
  onClose: () => void;
}

export default function KeyboardShortcutsModal({ open, onClose }: KeyboardShortcutsModalProps) {
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-sm px-4 animate-fade-in"
      >
        <div className="bg-[#212121] rounded-2xl shadow-[0_16px_48px_rgba(0,0,0,0.7)] overflow-hidden text-[#F2F2F2]">

          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4">
            <div className="flex items-center gap-2">
              <Command className="w-3.5 h-3.5 text-[#FFFFFF]" />
              <h2 id="shortcuts-title" className="text-[13px] font-semibold text-[#F2F2F2]">
                Keyboard Shortcuts
              </h2>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="p-1 text-[#BDBDBD] hover:text-[#F2F2F2] hover:bg-[#2a2a2a] rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Shortcuts */}
          <div className="px-5 py-4 space-y-5">
            {SHORTCUT_GROUPS.map((group) => (
              <div key={group.category}>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[#BDBDBD] mb-2.5">
                  {group.category}
                </p>
                <div className="space-y-1.5">
                  {group.shortcuts.map((s) => (
                    <div
                      key={s.description}
                      className="flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-[#2a2a2a] transition-colors"
                    >
                      <span className="text-[13px] text-[#F2F2F2]">{s.description}</span>
                      <div className="flex items-center gap-1">
                        {s.keys.map((k, i) => (
                          <span key={i} className="flex items-center gap-1">
                            <kbd className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-[#2a2a2a] text-[#BDBDBD] font-mono">
                              {k}
                            </kbd>
                            {i < s.keys.length - 1 && (
                              <span className="text-[10px] text-[#BDBDBD]">+</span>
                            )}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="px-5 py-3 bg-[#000000]/20">
            <p className="text-[11px] text-[#BDBDBD] text-center">
              Press{' '}
              <kbd className="inline-flex items-center px-1 py-0.5 rounded text-[10px] bg-[#2a2a2a] font-mono">
                Esc
              </kbd>{' '}
              to close
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
