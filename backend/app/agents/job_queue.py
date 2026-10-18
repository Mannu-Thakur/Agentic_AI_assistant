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
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.config import settings

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
        self._queue: asyncio.Queue = asyncio.Queue(
            maxsize=max(1, settings.MISSION_MAX_QUEUE_SIZE)
        )
        self._worker_task: Optional[asyncio.Task] = None
        self._started = False
        self._persistence_locks: Dict[str, asyncio.Lock] = {}
        self._persistence_tasks: set[asyncio.Task] = set()

    async def start_worker(self) -> None:
        """Restore durable jobs, then start the single in-process worker."""
        if not self._started:
            await self._recover_jobs()
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
        self._worker_task = None
        pending_saves = list(self._persistence_tasks)
        if pending_saves:
            _, pending = await asyncio.wait(pending_saves, timeout=5.0)
            if pending:
                logger.warning("[JobQueue] %d mission persistence task(s) did not finish before shutdown", len(pending))
        self._started = False
        logger.info("[JobQueue] Worker stopped")

    async def enqueue(
        self,
        query: str,
        user_id: str,
        session_id: str,
        model: str,
        api_keys: Dict[str, str],
    ) -> Job:
        """Create a job, add to queue, return immediately with job.id."""
        if not self._started:
            raise RuntimeError("Mission worker is not available")
        if self._queue.full():
            raise RuntimeError("Mission queue is full; please retry shortly")
        job = Job(
            id=str(uuid.uuid4()),
            query=query,
            user_id=user_id,
            session_id=session_id,
            model=model,
            api_keys=api_keys,
        )
        await self._create_persisted_job(job)
        self._jobs[job.id] = job
        self._queue.put_nowait(job)
        logger.info(f"[JobQueue] Enqueued job={job.id} user={user_id}")
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        cached = self._jobs.get(job_id)
        if cached:
            return cached
        return await self._load_job(job_id)

    async def user_jobs(self, user_id: str) -> List[Job]:
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.mission_job import MissionJob

        async with AsyncSessionLocal() as db:
            records = (await db.execute(
                select(MissionJob).where(MissionJob.user_id == user_id)
                .order_by(MissionJob.created_at.desc()).limit(100)
            )).scalars().all()
        jobs = [self._job_from_record(record) for record in records]
        self._jobs.update({job.id: job for job in jobs})
        return jobs

    def _emit(self, job: Job, event_type: str, data: Dict[str, Any]) -> None:
        """Push an event onto the job's event list and wake SSE consumers."""
        job.events.append(JobEvent(event_type=event_type, data=data))
        job._event_signal.set()
        self._schedule_save(job)

    def _schedule_save(self, job: Job) -> None:
        """Persist without delaying the live SSE stream; failures are logged."""
        task = asyncio.create_task(self._save_job(job))
        self._persistence_tasks.add(task)

        def report(task: asyncio.Task) -> None:
            self._persistence_tasks.discard(task)
            self._report_persist_failure(task)

        task.add_done_callback(report)

    @staticmethod
    def _report_persist_failure(task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error("[JobQueue] Could not persist mission state: %s", exc)

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
                # Clear only after draining events.  There is no await between
                # this clear and wait(), so an event emitted in between is never
                # lost; the prior implementation merely polled every 100 ms.
                job._event_signal.clear()
                if idx < len(job.events):
                    continue
                await asyncio.wait_for(
                    asyncio.shield(job._event_signal.wait()),
                    timeout=min(remaining, 5.0),
                )
            except asyncio.TimeoutError:
                pass

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
        await self._save_job(job)

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

        except asyncio.CancelledError:
            # Never re-run an interrupted LLM operation automatically: it may
            # have caused external work before the restart.  Surface a retryable
            # terminal result instead of leaving the job forever "running".
            job.status = "error"
            job.error = "Mission interrupted by server shutdown; please start a new mission."
            self._emit(job, "error", {"job_id": job.id, "error": job.error})
            raise
        except Exception as exc:
            logger.error(f"[JobQueue] Job {job.id} failed: {exc}", exc_info=True)
            job.status = "error"
            job.error  = str(exc)
            self._emit(job, "error", {"job_id": job.id, "error": str(exc)})

        finally:
            job.finished_at = time.time()
            await self._save_job(job)

    @staticmethod
    def _event_to_dict(event: JobEvent) -> Dict[str, Any]:
        return {
            "event_type": event.event_type,
            "data": event.data,
            "timestamp": event.timestamp,
        }

    @staticmethod
    def _event_from_dict(item: Dict[str, Any]) -> JobEvent:
        return JobEvent(
            event_type=str(item.get("event_type", "progress")),
            data=item.get("data") if isinstance(item.get("data"), dict) else {},
            timestamp=float(item.get("timestamp", time.time())),
        )

    def _job_from_record(self, record: Any) -> Job:
        from app.core.security import decrypt_api_key

        api_keys: Dict[str, str] = {}
        if record.encrypted_api_keys:
            try:
                decrypted = json.loads(decrypt_api_key(record.encrypted_api_keys))
                if isinstance(decrypted, dict):
                    api_keys = {str(k): str(v) for k, v in decrypted.items()}
            except Exception:
                logger.warning("[JobQueue] Could not decrypt transient keys for job=%s", record.id)

        created_at = record.created_at.timestamp() if record.created_at else time.time()
        finished_at = record.finished_at.timestamp() if record.finished_at else None
        raw_events = record.events if isinstance(record.events, list) else []
        return Job(
            id=record.id,
            query=record.query,
            user_id=record.user_id,
            session_id=record.session_id,
            model=record.model,
            api_keys=api_keys,
            status=record.status,
            events=[self._event_from_dict(event) for event in raw_events if isinstance(event, dict)],
            result=record.result,
            error=record.error,
            created_at=created_at,
            finished_at=finished_at,
        )

    async def _create_persisted_job(self, job: Job) -> None:
        from app.core.database import AsyncSessionLocal
        from app.core.security import encrypt_api_key
        from app.models.mission_job import MissionJob

        async with AsyncSessionLocal() as db:
            db.add(MissionJob(
                id=job.id,
                user_id=job.user_id,
                session_id=job.session_id,
                query=job.query,
                model=job.model,
                encrypted_api_keys=encrypt_api_key(json.dumps(job.api_keys)),
                status=job.status,
                events=[],
            ))
            await db.commit()

    async def _save_job(self, job: Job) -> None:
        from app.core.database import AsyncSessionLocal
        from app.models.mission_job import MissionJob

        lock = self._persistence_locks.setdefault(job.id, asyncio.Lock())
        async with lock:
            async with AsyncSessionLocal() as db:
                record = await db.get(MissionJob, job.id)
                if record is None:
                    return
                record.status = job.status
                record.events = [self._event_to_dict(event) for event in job.events]
                record.result = job.result
                record.error = job.error
                record.finished_at = (
                    datetime.fromtimestamp(job.finished_at, tz=timezone.utc)
                    if job.finished_at else None
                )
                await db.commit()

    async def _load_job(self, job_id: str) -> Optional[Job]:
        from app.core.database import AsyncSessionLocal
        from app.models.mission_job import MissionJob

        async with AsyncSessionLocal() as db:
            record = await db.get(MissionJob, job_id)
            if record is None:
                return None
            job = self._job_from_record(record)
        self._jobs[job.id] = job
        return job

    async def _recover_jobs(self) -> None:
        """Recover queued work and safely terminalize interrupted running work."""
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.mission_job import MissionJob

        async with AsyncSessionLocal() as db:
            records = (await db.execute(
                select(MissionJob).where(MissionJob.status.in_(["queued", "running", "awaiting_approval"]))
            )).scalars().all()
            for record in records:
                job = self._job_from_record(record)
                self._jobs[job.id] = job
                if job.status == "queued" and not self._queue.full():
                    self._queue.put_nowait(job)
                    continue
                job.status = "error"
                job.error = "Mission interrupted by server restart; please start a new mission."
                job.finished_at = time.time()
                record.status = job.status
                record.error = job.error
                record.finished_at = datetime.fromtimestamp(job.finished_at, tz=timezone.utc)
                record.events = [self._event_to_dict(event) for event in job.events]
            await db.commit()
        if records:
            logger.info("[JobQueue] Recovered %d durable mission record(s)", len(records))


# ── Singleton ─────────────────────────────────────────────────────────────────
job_queue = JobQueue()
