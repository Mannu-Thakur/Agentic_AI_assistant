/**
 * store/alertStore.ts — Zustand store for Proactive Intelligence alerts.
 *
 * Manages:
 *   - alerts[]        : list of fetched alert records
 *   - unreadCount     : badge number for the notification bell
 *   - isConnected     : SSE stream health indicator
 *   - sseStream       : the active EventSource instance
 *
 * Actions:
 *   - initSSE()       : open the SSE stream and start receiving alerts
 *   - closeSSE()      : gracefully close the SSE stream
 *   - fetchAlerts()   : REST fetch of stored alerts
 *   - markAllRead()   : mark all alerts as read
 *   - markOneRead()   : mark a single alert as read
 *   - prependAlert()  : add a real-time alert pushed via SSE
 */

import { create } from 'zustand';
import { BASE_URL } from '../services/api';
import { useAuthStore } from './authStore';

export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertType =
  | 'cross_document_match'
  | 'temporal_anomaly'
  | 'entity_collision'
  | 'drift_detected'
  | 'high_hallucination_rate'
  | 'cost_spike'
  | 'morning_briefing';

export interface ProactiveAlert {
  id: string;
  alert_id: string;
  alert_type: AlertType;
  severity: AlertSeverity;
  title: string;
  message: string;
  confidence: number;
  entity_key: string;
  source_doc_ids: string[];
  metadata: Record<string, unknown>;
  is_read: boolean;
  created_at: number;
}

interface AlertState {
  alerts: ProactiveAlert[];
  unreadCount: number;
  isConnected: boolean;
  isLoading: boolean;

  initSSE: () => void;
  closeSSE: () => void;
  fetchAlerts: () => Promise<void>;
  fetchUnreadCount: () => Promise<void>;
  markAllRead: () => Promise<void>;
  markOneRead: (recordId: string) => Promise<void>;
  prependAlert: (alert: ProactiveAlert) => void;
}

// Singleton EventSource reference kept outside store (not serializable)
let _eventSource: EventSource | null = null;

export const useAlertStore = create<AlertState>((set, get) => ({
  alerts: [],
  unreadCount: 0,
  isConnected: false,
  isLoading: false,

  // ── SSE connection ──────────────────────────────────────────────────────────
  initSSE: () => {
    const token = useAuthStore.getState().token;
    if (!token || _eventSource) return;

    const url = `${BASE_URL}/proactive/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    _eventSource = es;

    es.addEventListener('connected', () => {
      set({ isConnected: true });
      // Fetch existing alerts + badge count on connect
      get().fetchAlerts();
      get().fetchUnreadCount();
    });

    es.addEventListener('alert', (e: MessageEvent) => {
      try {
        const alert = JSON.parse(e.data) as ProactiveAlert;
        get().prependAlert(alert);
        set((s) => ({ unreadCount: s.unreadCount + 1 }));
      } catch {
        // malformed event — ignore
      }
    });

    es.addEventListener('ping', () => {
      // keepalive — no action needed
    });

    es.onerror = () => {
      set({ isConnected: false });
      // Auto-reconnect after 5s
      es.close();
      _eventSource = null;
      setTimeout(() => get().initSSE(), 5000);
    };
  },

  closeSSE: () => {
    if (_eventSource) {
      _eventSource.close();
      _eventSource = null;
    }
    set({ isConnected: false });
  },

  // ── REST: fetch stored alerts ───────────────────────────────────────────────
  fetchAlerts: async () => {
    set({ isLoading: true });
    try {
      const token = useAuthStore.getState().token;
      const res = await fetch(`${BASE_URL}/proactive/alerts?limit=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: ProactiveAlert[] = await res.json();
        set({ alerts: data });
      }
    } catch {
      // non-fatal
    } finally {
      set({ isLoading: false });
    }
  },

  // ── REST: badge count ───────────────────────────────────────────────────────
  fetchUnreadCount: async () => {
    try {
      const token = useAuthStore.getState().token;
      const res = await fetch(`${BASE_URL}/proactive/alerts/unread-count`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        set({ unreadCount: data.count ?? 0 });
      }
    } catch {
      // non-fatal
    }
  },

  // ── REST: mark all read ─────────────────────────────────────────────────────
  markAllRead: async () => {
    const token = useAuthStore.getState().token;
    await fetch(`${BASE_URL}/proactive/alerts/mark-read`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    set((s) => ({
      unreadCount: 0,
      alerts: s.alerts.map((a) => ({ ...a, is_read: true })),
    }));
  },

  // ── REST: mark one read ─────────────────────────────────────────────────────
  markOneRead: async (recordId: string) => {
    const token = useAuthStore.getState().token;
    await fetch(`${BASE_URL}/proactive/alerts/mark-read`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ alert_record_id: recordId }),
    });
    set((s) => ({
      unreadCount: Math.max(0, s.unreadCount - 1),
      alerts: s.alerts.map((a) => (a.id === recordId ? { ...a, is_read: true } : a)),
    }));
  },

  // ── In-memory: prepend a live alert ─────────────────────────────────────────
  prependAlert: (alert: ProactiveAlert) => {
    set((s) => ({
      alerts: [{ ...alert, is_read: false }, ...s.alerts].slice(0, 100),
    }));
  },
}));
