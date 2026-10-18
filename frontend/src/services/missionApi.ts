/**
 * missionApi.ts — Mission Mode API client (v2 — job queue based)
 *
 * Flow:
 *   1. POST /mission/run  → {job_id, stream_url}   (returns immediately)
 *   2. GET  /mission/{id}/stream  → SSE events      (reconnectable)
 *   3. GET  /mission/{id}         → final status     (polling fallback)
 */

import { BASE_URL } from './api';
import { apiRequestWithWakeup } from './api';

export interface MissionRunRequest {
  query: string;
  model?: string;
  session_id?: string;
}

export interface MissionRunResponse {
  job_id: string;
  status: string;
  stream_url: string;
  query: string;
}

export interface MissionSSEEvent {
  type:
    | 'mission_started'
    | 'mission_classified'
    | 'agent_done'
    | 'critic_done'
    | 'hitl_required'
    | 'mission_complete'
    | 'mission_delegated'
    | 'error';
  data: Record<string, any>;
}

export type MissionEventHandler = (event: MissionSSEEvent) => void;

/**
 * Step 1 — Enqueue a mission. Returns job_id immediately.
 */
export async function enqueueMission(
  req: MissionRunRequest,
  token: string,
  apiKeys: Record<string, string>,
): Promise<MissionRunResponse> {
  return apiRequestWithWakeup<MissionRunResponse>('/mission/run', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'x-api-keys':    JSON.stringify(apiKeys),
    },
    json: req,
    timeoutMs: 60_000,
  });
}

/**
 * Step 2 — Stream SSE events for a job. Calls onEvent for each.
 * Supports Last-Event-ID for reconnection.
 * Returns a cleanup function.
 */
export function streamMissionEvents(
  jobId: string,
  token: string,
  onEvent: MissionEventHandler,
  lastEventId?: string,
): () => void {
  let stopped = false;
  let retryCount = 0;
  let lastSeenEventId = lastEventId || '';
  let activeController: AbortController | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  const connect = async () => {
    while (!stopped) {
      const controller = new AbortController();
      activeController = controller;
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
      if (lastSeenEventId) headers['Last-Event-ID'] = lastSeenEventId;

      try {
        const res = await fetch(`${BASE_URL}/mission/${jobId}/stream`, {
          headers,
          signal: controller.signal,
          cache: 'no-store',
        });
        if (!res.ok || !res.body) {
          onEvent({ type: 'error', data: { error: `Mission progress stream returned HTTP ${res.status}.` } });
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEvent = '';
        let currentData = '';

        while (!stopped) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('id: ')) {
              lastSeenEventId = line.slice(4).trim();
            } else if (line.startsWith('event: ')) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ')) {
              currentData = currentData ? `${currentData}\n${line.slice(6).trim()}` : line.slice(6).trim();
            } else if (line === '' && currentEvent && currentData) {
              try {
                const parsed = JSON.parse(currentData);
                onEvent({
                  type: (parsed.event_type || currentEvent) as MissionSSEEvent['type'],
                  data: parsed,
                });
              } catch {
                // Ignore malformed events; keep the stream alive for later updates.
              }
              currentEvent = '';
              currentData = '';
            }
          }
        }
        if (stopped) return;
      } catch (error: any) {
        if (stopped || error?.name === 'AbortError') return;
      }

      if (retryCount >= 2) {
        onEvent({
          type: 'error',
          data: { error: 'Live mission updates disconnected. Checking the saved mission result…' },
        });
        return;
      }

      retryCount += 1;
      await new Promise<void>((resolve) => {
        retryTimer = setTimeout(() => {
          retryTimer = null;
          resolve();
        }, 600 * retryCount);
      });
    }
  };

  void connect();
  return () => {
    stopped = true;
    activeController?.abort();
    if (retryTimer) clearTimeout(retryTimer);
  };
}

/**
 * Step 3 — Poll final job status (fallback / periodic check).
 */
export async function getMissionStatus(jobId: string, token: string): Promise<any> {
  try {
    return await apiRequestWithWakeup(`/mission/${jobId}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
  } catch {
    return null;
  }
}

/**
 * Get all missions for the current user.
 */
export async function listMissions(token: string): Promise<any[]> {
  const res = await fetch(`${BASE_URL}/mission/`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.missions || [];
}

/**
 * Approve a HITL request.
 */
export async function approveHITL(
  missionId: string,
  token: string,
  reason?: string,
): Promise<void> {
  await fetch(`${BASE_URL}/hitl/approve/${missionId}`, {
    method: 'POST',
    headers: {
      'Content-Type':  'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ reason }),
  });
}

/**
 * Reject a HITL request.
 */
export async function rejectHITL(
  missionId: string,
  token: string,
  reason?: string,
): Promise<void> {
  await fetch(`${BASE_URL}/hitl/reject/${missionId}`, {
    method: 'POST',
    headers: {
      'Content-Type':  'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ reason }),
  });
}

/**
 * Persist the completed mission as real DB messages so they survive refresh.
 */
export async function persistMission(
  token: string,
  payload: {
    chat_id:      string;
    query:        string;
    response:     string;
    model:        string;
    critic_score: number;
    agent_names:  string[];
    artifacts:    any[];
    job_id?:      string;
  },
): Promise<{ user_message_id: string; assistant_message_id: string } | null> {
  try {
    const res = await fetch(`${BASE_URL}/mission/persist`, {
      method: 'POST',
      headers: {
        'Content-Type':  'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

