import { useEffect, useCallback } from 'react';

interface ShortcutHandlers {
  onNewChat?: () => void;
  onOpenSearch?: () => void;
  onShowShortcuts?: () => void;
  onEscape?: () => void;
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const ctrl = e.ctrlKey || e.metaKey;
    const target = e.target as HTMLElement;
    const inInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;

    // Ctrl+N — New Chat (only if not in input)
    if (ctrl && e.key === 'n' && !inInput) {
      e.preventDefault();
      handlers.onNewChat?.();
      return;
    }

    // Ctrl+K — Global Search
    if (ctrl && e.key === 'k') {
      e.preventDefault();
      handlers.onOpenSearch?.();
      return;
    }

    // Ctrl+/ — Keyboard shortcuts reference
    if (ctrl && e.key === '/') {
      e.preventDefault();
      handlers.onShowShortcuts?.();
      return;
    }

    // Escape — Close any open overlay
    if (e.key === 'Escape') {
      handlers.onEscape?.();
      return;
    }
  }, [handlers]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}
