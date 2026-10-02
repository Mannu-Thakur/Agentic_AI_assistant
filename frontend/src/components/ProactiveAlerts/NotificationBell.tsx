/**
 * components/ProactiveAlerts/NotificationBell.tsx
 *
 * The 🔔 notification bell button rendered in the top-right corner of the UI.
 *
 * Behaviour:
 *  - Shows red badge with unread count (hidden when 0).
 *  - Pulses when a new alert arrives and panel is closed.
 *  - Clicking opens/closes the AlertPanel dropdown.
 *  - Clicking outside closes the panel.
 *  - Connects to SSE stream on mount (via alertStore.initSSE).
 *  - Shows a tiny green dot when SSE is connected.
 */

import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { useAlertStore } from '../../store/alertStore';
import { useAuthStore } from '../../store/authStore';
import { AlertPanel } from './AlertPanel';

export function NotificationBell() {
  const { unreadCount, isConnected, initSSE, closeSSE } = useAlertStore();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [open, setOpen] = useState(false);
  const [pulse, setPulse] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const prevUnread = useRef(unreadCount);

  // Connect SSE when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      initSSE();
    }
    return () => closeSSE();
  }, [isAuthenticated]);

  // Pulse animation when new alert arrives while panel is closed
  useEffect(() => {
    if (unreadCount > prevUnread.current && !open) {
      setPulse(true);
      const t = setTimeout(() => setPulse(false), 2000);
      prevUnread.current = unreadCount;
      return () => clearTimeout(t);
    }
    prevUnread.current = unreadCount;
  }, [unreadCount, open]);

  // Close panel when clicking outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  if (!isAuthenticated) return null;

  return (
    <div ref={containerRef} className="relative">
      {/* Bell button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className={`relative p-2 rounded-lg text-white/60 hover:text-white hover:bg-white/8
          transition-all duration-200 ${pulse ? 'animate-bounce' : ''}`}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        title="Proactive Intelligence Alerts"
      >
        <Bell className={`w-5 h-5 ${open ? 'text-white' : ''}`} />

        {/* Unread badge */}
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1
            bg-red-500 text-white text-[9px] font-bold rounded-full
            flex items-center justify-center leading-none shadow-sm">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}

        {/* SSE connection indicator dot */}
        <span
          className={`absolute bottom-1 right-1 w-1.5 h-1.5 rounded-full
            ${isConnected ? 'bg-emerald-400' : 'bg-zinc-500'}`}
          title={isConnected ? 'Live alerts connected' : 'Reconnecting…'}
        />
      </button>

      {/* Dropdown panel */}
      {open && <AlertPanel onClose={() => setOpen(false)} />}
    </div>
  );
}
