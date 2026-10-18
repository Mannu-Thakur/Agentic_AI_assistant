/**
 * useMission.ts — React hook for Mission Mode (v2)
 *
 * Gap 1 Fix: Mission final response is now properly injected into the
 * chat thread as an assistant message using the chatStore.addMessage().
 *
 * Architecture:
 *   POST /mission/run → job_id (immediate)
 *   GET  /mission/{id}/stream → SSE events (background)
 *   onFinalResponse → addMessage() to inject into chat
 */

import { useState, useCallback, useRef } from 'react';
import { useAuthStore } from '../store/authStore';
import { useChatStore } from '../store/chatStore';
import {
  enqueueMission,
  streamMissionEvents,
  approveHITL,
  rejectHITL,
  persistMission,
  getMissionStatus,
  MissionSSEEvent,
} from '../services/missionApi';
import type { Message } from '../types/chat';

export type MissionStatus =
  | 'idle'
  | 'queued'
  | 'classifying'
  | 'running'
  | 'awaiting_approval'
  | 'complete'
  | 'delegated'
  | 'error';

export interface AgentStepState {
  agent: string;
  status: 'running' | 'done' | 'failed';
  output?: string;
  artifacts?: any[];
  duration_ms?: number;
}

export interface MissionState {
  status: MissionStatus;
  jobId: string;
  missionId: string;
  agentSteps: AgentStepState[];
  artifacts: any[];
  critcResult: { score: number; passes: boolean; feedback: string } | null;
  hitlRequest: {
    mission_id: string;
    reason: string;
    approve_url: string;
    reject_url: string;
  } | null;
  finalResponse: string;
  error: string;
  isDelegated: boolean;
  planReason: string;       // why the planner selected these agents
  retryCount: number;       // how many critic retries have occurred
}

const INITIAL: MissionState = {
  status:        'idle',
  jobId:         '',
  missionId:     '',
  agentSteps:    [],
  artifacts:     [],
  critcResult:   null,
  hitlRequest:   null,
  finalResponse: '',
  error:         '',
  isDelegated:   false,
  planReason:    '',
  retryCount:    0,
};

interface MissionCallbacks {
  onDelegated?: () => void;
  onMissionAccepted?: () => void;
}

export function useMission() {
  const [mission, setMission] = useState<MissionState>(INITIAL);
  const cleanupRef = useRef<(() => void) | null>(null);
  const { token }  = useAuthStore();

  // Chat store — used to inject mission response as assistant message
  const addMessage   = useChatStore(s => s.addMessage);
  const activeChatId = useChatStore(s => s.activeChatId);

  const startMission = useCallback(async (
    query: string,
    model: string,
    sessionId: string,
    apiKeys: Record<string, string>,
    callbacks: MissionCallbacks = {},
  ) => {
    if (!token) return;

    // Cancel any previous mission stream
    cleanupRef.current?.();
    cleanupRef.current = null;

    setMission({ ...INITIAL, status: 'queued' });

    // ── Step 1: Enqueue — returns job_id immediately ──────────────────────────
    let jobId = '';
    try {
      const res = await enqueueMission(
        { query, model, session_id: sessionId },
        token,
        apiKeys,
      );
      jobId = res.job_id;
      setMission(prev => ({
        ...prev,
        status:    'classifying',
        jobId,
        missionId: jobId,
      }));
    } catch (err: any) {
      setMission(prev => ({
        ...prev,
        status: 'error',
        error:  err.message || 'Mission enqueue failed',
      }));
      return;
    }

    // sessionId is the chat selected by the caller. It also covers a mission
    // launched from the welcome view, where this hook's activeChatId closure
    // may still be null until React renders the newly created chat.
    const missionChatId = sessionId || activeChatId;
    let statusPollCancelled = false;
    let statusPollStarted = false;
    let terminalHandled = false;
    let recoverMissionStatus: () => void = () => {};

    // A reconnect can replay classification events. Keep route callbacks
    // idempotent so one mission can never recursively enqueue duplicate chats.
    let delegatedNotified = false;
    let missionAcceptedNotified = false;
    const notifyDelegated = () => {
      if (delegatedNotified) return;
      delegatedNotified = true;
      callbacks.onDelegated?.();
    };
    const notifyMissionAccepted = () => {
      if (missionAcceptedNotified) return;
      missionAcceptedNotified = true;
      callbacks.onMissionAccepted?.();
    };

    // ── Step 2: Subscribe to SSE stream ──────────────────────────────────────
    const handleEvent = (event: MissionSSEEvent) => {
      const { type, data } = event;

      if (type === 'mission_classified') {
        const agents: string[] = data.agents || [];
        setMission(prev => ({
          ...prev,
          status: data.is_mission ? 'running' : 'delegated',
          planReason: data.plan_reason || '',
          agentSteps: agents.map(agent => ({
            agent,
            status: 'running' as const,
          })),
        }));
        if (data.is_mission) notifyMissionAccepted();
        else notifyDelegated();
      }

      else if (type === 'agent_done') {
        setMission(prev => ({
          ...prev,
          agentSteps: prev.agentSteps.map(step =>
            step.agent === data.agent
              ? { ...step, status: data.success ? 'done' : 'failed', artifacts: data.artifacts || [] }
              : step
          ),
          artifacts: [...prev.artifacts, ...(data.artifacts || [])],
        }));
      }

      else if (type === 'critic_done') {
        setMission(prev => ({
          ...prev,
          retryCount: data.retry_count ?? prev.retryCount,
          critcResult: {
            score:    data.score   ?? 0.8,
            passes:   data.passes  ?? true,
            feedback: data.feedback ?? '',
          },
        }));
      }

      else if (type === 'hitl_required') {
        setMission(prev => ({
          ...prev,
          status: 'awaiting_approval',
          hitlRequest: {
            mission_id:  data.job_id || jobId,
            reason:      data.reason || 'Human approval required before proceeding.',
            approve_url: data.approve_url || '',
            reject_url:  data.reject_url  || '',
          },
        }));
      }

      else if (type === 'mission_complete') {
        if (terminalHandled) return;
        terminalHandled = true;
        statusPollCancelled = true;
        const finalResponse: string = data.response || '';
        if (finalResponse) notifyMissionAccepted();

        setMission(prev => {
          const updated = {
            ...prev,
            status:        'complete' as MissionStatus,
            finalResponse,
            artifacts:     [...prev.artifacts, ...(data.artifacts || [])],
            hitlRequest:   null,
          };

          // ── Inject into chat thread (in-memory) ──────────────────────────
          if (finalResponse && missionChatId) {
            const missionMessage: Message = {
              id:                `mission-${jobId}-${Date.now()}`,
              chat_id:           missionChatId,
              parent_id:         null,
              role:              'assistant',
              content:           finalResponse,
              tool_calls:        null,
              created_at:        new Date().toISOString(),
              developer_metrics: {
                model_used:       model,
                latency_ms:       0,
                tokens_input:     0,
                tokens_output:    0,
                cost_estimate:    0,
                confidence_score: data.critic_score ?? 0.8,
                memory_hits:      0,
                generation_mode:  'normal_rag',
              },
            };
            addMessage(missionMessage);
          }

          return updated;
        });

        // ── Persist to DB so it survives page refresh ─────────────────────
        if (finalResponse && missionChatId && token) {
          persistMission(token, {
            chat_id:      missionChatId,
            query,
            response:     finalResponse,
            model,
            critic_score: data.critic_score ?? 0.8,
            agent_names:  data.agents || [],
            artifacts:    data.artifacts || [],
            job_id:       jobId,
          }).catch(err => console.warn('[useMission] persist failed:', err));
        }
      }

      else if (type === 'mission_delegated') {
        terminalHandled = true;
        statusPollCancelled = true;
        setMission(prev => ({ ...prev, status: 'delegated', isDelegated: true }));
        notifyDelegated();
      }

      else if (type === 'error') {
        recoverMissionStatus();
      }
    };

    // SSE is the real-time path. If a host/proxy closes that connection, poll
    // the authenticated job record until it reaches a terminal state so the
    // user still receives the mission result instead of a transient network error.
    recoverMissionStatus = () => {
      if (statusPollStarted || terminalHandled) return;
      statusPollStarted = true;
      setMission(prev => ({
        ...prev,
        error: 'Live progress disconnected; checking the saved mission status…',
      }));

      void (async () => {
        let unavailableAttempts = 0;
        for (let attempt = 0; attempt < 45 && !statusPollCancelled; attempt += 1) {
          await new Promise(resolve => setTimeout(resolve, 2_000));
          if (statusPollCancelled) return;
          const status = await getMissionStatus(jobId, token);
          if (!status) {
            unavailableAttempts += 1;
            if (unavailableAttempts >= 3) break;
            continue;
          }
          unavailableAttempts = 0;

          if (status.status === 'complete') {
            if (status.result) {
              handleEvent({ type: 'mission_complete', data: {
                job_id: jobId,
                response: status.result,
              } });
            } else if (!missionAcceptedNotified) {
              terminalHandled = true;
              statusPollCancelled = true;
              setMission(prev => ({ ...prev, status: 'delegated', isDelegated: true, error: '' }));
              notifyDelegated();
            } else {
              terminalHandled = true;
              statusPollCancelled = true;
              setMission(prev => ({ ...prev, status: 'error', error: 'Mission completed without a response.' }));
            }
            return;
          }

          if (status.status === 'error') {
            terminalHandled = true;
            statusPollCancelled = true;
            setMission(prev => ({ ...prev, status: 'error', error: status.error || 'Mission failed.' }));
            return;
          }
        }

        if (!statusPollCancelled) {
          terminalHandled = true;
          setMission(prev => ({ ...prev, status: 'error', error: 'Could not reconnect to the mission service. Please retry this task.' }));
        }
      })();
    };

    const cleanup = streamMissionEvents(jobId, token, handleEvent);
    cleanupRef.current = () => {
      statusPollCancelled = true;
      cleanup();
    };

  }, [token, activeChatId, addMessage]);

  const handleApprove = useCallback(async () => {
    const { jobId } = mission;
    if (!jobId || !token) return;
    setMission(prev => ({ ...prev, status: 'running', hitlRequest: null }));
    await approveHITL(jobId, token, 'Approved by user');
  }, [mission, token]);

  const handleReject = useCallback(async () => {
    const { jobId } = mission;
    if (!jobId || !token) return;
    const rejectMsg = 'Action was rejected by the user and will not be executed.';
    setMission(prev => ({
      ...prev,
      status:        'complete',
      hitlRequest:   null,
      finalResponse: rejectMsg,
    }));
    // Inject rejection notice into chat
    if (activeChatId) {
      addMessage({
        id:                `mission-reject-${Date.now()}`,
        chat_id:           activeChatId,
        parent_id:         null,
        role:              'assistant',
        content:           `⚠️ **Mission action rejected.** ${rejectMsg}`,
        tool_calls:        null,
        created_at:        new Date().toISOString(),
        developer_metrics: null,
      });
    }
    await rejectHITL(jobId, token, 'Rejected by user');
  }, [mission, token, activeChatId, addMessage]);

  const reset = useCallback(() => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    setMission(INITIAL);
  }, []);

  return {
    mission,
    startMission,
    handleApprove,
    handleReject,
    reset,
    isActive: !['idle', 'complete', 'error', 'delegated'].includes(mission.status),
  };
}
