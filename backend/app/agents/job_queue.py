"""
app/agents/job_queue.py — Async Background Job Queue

Provides a simple asyncio-based job queue so mission runs don't hold
HTTP connections open. The client gets a job_id immediately, then
reconnects to a per-job SSE stream to receive progress updates.

Architecture
------------
  POST /api/v1/mission/run   → enqueues job, returns job_id immediately
  GET  /api/v1/mission/{id}/stream → SSE stream of progress events
  GET  /api/v1/mission/{id}  → final status + result

Worker loop
-----------
  A single asyncio.Task processes jobs from the queue, running the
  Supervisor graph and writing events to a per-job in-memory event list
  that SSE consumers can tail.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger("agents.job_queue")


@dataclass
class JobEvent:
    event_type: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class Job:
    id: str
    query: str
    user_id: str
    session_id: str
    model: str
    api_keys: Dict[str, str]
    status: str = "queued"          # queued | running | complete | error | awaiting_approval
    events: List[JobEvent] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    # Notify SSE subscribers when a new event arrives
    _event_signal: asyncio.Event = field(default_factory=asyncio.Event)


class JobQueue:
    """
    Simple single-process async job queue.
    In production, replace with Redis Streams or Celery.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._started = False

    def start_worker(self) -> None:
        """Start the background worker. Call once from FastAPI lifespan."""
        if not self._started:
            self._worker_task = asyncio.create_task(self._worker_loop(), name="mission_worker")
            self._started = True
            logger.info("[JobQueue] Worker started")

    async def stop_worker(self) -> None:
        """Graceful shutdown."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("[JobQueue] Worker stopped")

    def enqueue(
        self,
        query: str,
        user_id: str,
        session_id: str,
        model: str,
        api_keys: Dict[str, str],
    ) -> Job:
        """Create a job, add to queue, return immediately with job.id."""
        job = Job(
            id=str(uuid.uuid4())[:12],
            query=query,
            user_id=user_id,
            session_id=session_id,
            model=model,
            api_keys=api_keys,
        )
        self._jobs[job.id] = job
        self._queue.put_nowait(job)
        logger.info(f"[JobQueue] Enqueued job={job.id} user={user_id}")
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def user_jobs(self, user_id: str) -> List[Job]:
        return [j for j in self._jobs.values() if j.user_id == user_id]

    def _emit(self, job: Job, event_type: str, data: Dict[str, Any]) -> None:
        """Push an event onto the job's event list and wake SSE consumers."""
        job.events.append(JobEvent(event_type=event_type, data=data))
        job._event_signal.set()
        job._event_signal.clear()

    async def tail_events(
        self,
        job_id: str,
        from_index: int = 0,
        timeout: float = 180.0,
    ) -> AsyncGenerator[JobEvent, None]:
        """
        Async generator that yields events as they arrive.
        Call with from_index=0 to receive all events from the start.
        """
        job = self._jobs.get(job_id)
        if not job:
            return

        idx = from_index
        deadline = time.time() + timeout

        while True:
            # Yield any buffered events first
            while idx < len(job.events):
                yield job.events[idx]
                idx += 1

            # Stop if job is done
            if job.status in ("complete", "error"):
                break

            # Wait for next event signal (with timeout)
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            try:
                await asyncio.wait_for(
                    asyncio.shield(self._wait_for_signal(job)),
                    timeout=min(remaining, 5.0),
                )
            except asyncio.TimeoutError:
                pass

    async def _wait_for_signal(self, job: Job) -> None:
        """Wait until the job emits a new event."""
        signal = asyncio.Event()
        # Re-check: new events may already be waiting
        if len(job.events) > 0:
            return
        await asyncio.sleep(0.1)

    async def _worker_loop(self) -> None:
        """Continuously processes jobs from the queue."""
        while True:
            try:
                job: Job = await self._queue.get()
                await self._process_job(job)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[JobQueue] Worker error: {exc}", exc_info=True)
                await asyncio.sleep(1)

    async def _process_job(self, job: Job) -> None:
        """Run the Supervisor graph for a job, emitting events as it proceeds."""
        logger.info(f"[JobQueue] Processing job={job.id}")
        job.status = "running"

        self._emit(job, "mission_started", {
            "job_id":    job.id,
            "query":     job.query,
            "timestamp": time.time(),
        })

        async def _run_graph(graph) -> None:
            """Stream supervisor graph events and emit them onto the job."""
            initial_state: dict = {
                "query":            job.query,
                "user_id":          job.user_id,
                "session_id":       job.session_id,
                "active_model":     job.model,
                "api_keys":         job.api_keys,
                "messages":         [],
                "supervisor_trace": [],
                "artifacts":        [],
            }
            config = {
                "configurable": {
                    "thread_id": f"{job.user_id}:{job.session_id}:{job.id}",
                }
            }

            async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if node_name == "supervisor_classify":
                        self._emit(job, "mission_classified", {
                            "job_id":      job.id,
                            "is_mission":  node_output.get("is_mission", False),
                            "agents":      node_output.get("selected_agents", []),
                            "plan_reason": node_output.get("plan_reasoning", ""),
                        })
                    elif node_name == "parallel_dispatch":
                        for agent_name, result in (node_output.get("agent_results") or {}).items():
                            self._emit(job, "agent_done", {
                                "job_id":    job.id,
                                "agent":     agent_name,
                                "success":   result.get("success", False),
                                "artifacts": result.get("artifacts", []),
                            })
                    elif node_name == "critic_verification":
                        self._emit(job, "critic_done", {
                            "job_id":   job.id,
                            "score":    node_output.get("critic_score", 0.0),
                            "passes":   node_output.get("critic_passes", True),
                            "feedback": (node_output.get("critic_feedback") or "")[:300],
                        })
                    elif node_name == "synthesizer":
                        final = node_output.get("final_response", "")
                        job.result = final
                        self._emit(job, "mission_complete", {
                            "job_id":    job.id,
                            "response":  final,
                            "artifacts": node_output.get("artifacts", []),
                        })
                    elif node_name == "delegate":
                        self._emit(job, "mission_delegated", {
                            "job_id": job.id,
                            "reason": "Simple query — use standard chat endpoint",
                        })

        try:
            # Prefer AsyncSqliteSaver (true persistence across restarts)
            try:
                from app.agents.supervisor import get_supervisor_with_sqlite
                async for graph in get_supervisor_with_sqlite():
                    await _run_graph(graph)
            except Exception as sqlite_err:
                logger.warning(
                    f"[JobQueue] SQLite checkpointer unavailable ({sqlite_err}), "
                    "falling back to MemorySaver graph"
                )
                from app.agents.supervisor import supervisor_graph
                await _run_graph(supervisor_graph)

            job.status = "complete"

        except Exception as exc:
            logger.error(f"[JobQueue] Job {job.id} failed: {exc}", exc_info=True)
            job.status = "error"
            job.error  = str(exc)
            self._emit(job, "error", {"job_id": job.id, "error": str(exc)})

        finally:
            job.finished_at = time.time()


# ── Singleton ─────────────────────────────────────────────────────────────────
job_queue = JobQueue()
