/**
 * missionApi.ts — Mission Mode API client (v2 — job queue based)
 *
 * Flow:
 *   1. POST /mission/run  → {job_id, stream_url}   (returns immediately)
 *   2. GET  /mission/{id}/stream  → SSE events      (reconnectable)
 *   3. GET  /mission/{id}         → final status     (polling fallback)
 */

import { BASE_URL } from './api';

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
  const res = await fetch(`${BASE_URL}/api/v1/mission/run`, {
    method: 'POST',
    headers: {
      'Content-Type':  'application/json',
      'Authorization': `Bearer ${token}`,
      'x-api-keys':    JSON.stringify(apiKeys),
    },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Mission enqueue failed: ${res.status} ${text}`);
  }

  return res.json();
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
  const headers: Record<string, string> = {
    'Authorization': `Bearer ${token}`,
  };
  if (lastEventId) {
    headers['Last-Event-ID'] = lastEventId;
  }

  // Use fetch-based SSE for auth header support
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/v1/mission/${jobId}/stream`, {
        headers,
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        onEvent({ type: 'error', data: { error: `Stream failed: ${res.status}` } });
        return;
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = '';
        let currentData  = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6).trim();
          } else if (line === '' && currentEvent && currentData) {
            try {
              const parsed = JSON.parse(currentData);
              onEvent({
                type: (parsed.event_type || currentEvent) as MissionSSEEvent['type'],
                data: parsed,
              });
            } catch {
              // ignore parse error
            }
            currentEvent = '';
            currentData  = '';
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        onEvent({ type: 'error', data: { error: String(e) } });
      }
    }
  })();

  return () => controller.abort();
}

/**
 * Step 3 — Poll final job status (fallback / periodic check).
 */
export async function getMissionStatus(jobId: string, token: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/api/v1/mission/${jobId}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}

/**
 * Get all missions for the current user.
 */
export async function listMissions(token: string): Promise<any[]> {
  const res = await fetch(`${BASE_URL}/api/v1/mission/`, {
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
  await fetch(`${BASE_URL}/api/v1/hitl/approve/${missionId}`, {
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
  await fetch(`${BASE_URL}/api/v1/hitl/reject/${missionId}`, {
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
    const res = await fetch(`${BASE_URL}/api/v1/mission/persist`, {
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

