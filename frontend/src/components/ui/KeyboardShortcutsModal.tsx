import { useEffect, useRef } from 'react';
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
  const overlayRef = useRef<HTMLDivElement>(null);

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
        ref={overlayRef}
        className="search-overlay-bg"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        className="search-panel"
      >
        <div className="glass-heavy rounded-2xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <div className="flex items-center gap-2.5">
              <Command className="w-4 h-4 text-accent" />
              <h2 id="shortcuts-title" className="text-sm font-semibold text-foreground">
                Keyboard Shortcuts
              </h2>
            </div>
            <button
              onClick={onClose}
              aria-label="Close keyboard shortcuts"
              className="p-1.5 rounded-lg text-foreground-3 hover:text-foreground hover:bg-surface-2 transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Shortcuts list */}
          <div className="p-5 space-y-5">
            {SHORTCUT_GROUPS.map((group) => (
              <div key={group.category}>
                <p className="text-[10px] font-bold uppercase tracking-widest text-foreground-3 mb-3">
                  {group.category}
                </p>
                <div className="space-y-2">
                  {group.shortcuts.map((s) => (
                    <div
                      key={s.description}
                      className="flex items-center justify-between py-1.5 px-1"
                    >
                      <span className="text-sm text-foreground-2">{s.description}</span>
                      <div className="flex items-center gap-1">
                        {s.keys.map((k, i) => (
                          <span key={i} className="flex items-center gap-1">
                            <kbd className="kbd">{k}</kbd>
                            {i < s.keys.length - 1 && (
                              <span className="text-[10px] text-foreground-3">+</span>
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

          <div className="px-5 py-3 border-t border-border bg-surface-2/50">
            <p className="text-[11px] text-foreground-3 text-center">
              Press <kbd className="kbd">Esc</kbd> to close
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
