"""
app/proactive/broadcaster.py — In-process SSE connection manager.

Maintains a registry of active SSE connections keyed by user_id.
When an alert is ready to push, broadcast_to_user() sends it to all
open SSE streams for that user (typically 1 tab, possibly more).

Design notes
────────────
• Pure asyncio — no Redis pub/sub needed for single-process deployments.
• Multi-tab safe: all open connections for a user receive the same event.
• Thread-safe: asyncio.Lock guards the connection dict.
• Self-cleaning: disconnected queues are pruned automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List

logger = logging.getLogger("app.proactive.broadcaster")

# user_id → list of asyncio.Queue instances (one per open SSE connection)
_connections: Dict[str, List[asyncio.Queue]] = {}
_lock = asyncio.Lock()


async def register(user_id: str) -> asyncio.Queue:
    """Register a new SSE connection for user_id. Returns the queue to read from."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    async with _lock:
        _connections.setdefault(user_id, []).append(queue)
    logger.debug(f"[Broadcaster] +connection user={user_id[:8]} total={len(_connections.get(user_id, []))}")
    return queue


async def deregister(user_id: str, queue: asyncio.Queue) -> None:
    """Remove a closed SSE connection."""
    async with _lock:
        conns = _connections.get(user_id, [])
        try:
            conns.remove(queue)
        except ValueError:
            pass
        if not conns:
            _connections.pop(user_id, None)
    logger.debug(f"[Broadcaster] -connection user={user_id[:8]}")


async def broadcast_to_user(user_id: str, alert_dict: dict) -> int:
    """
    Push an alert to all open SSE connections for user_id.
    Returns the number of connections that received it.
    Stale/full queues are pruned from the registry.
    """
    payload = json.dumps(alert_dict)
    sent = 0
    stale: List[asyncio.Queue] = []

    async with _lock:
        conns = list(_connections.get(user_id, []))

    for q in conns:
        try:
            q.put_nowait(payload)
            sent += 1
        except asyncio.QueueFull:
            logger.warning(f"[Broadcaster] Queue full for user={user_id[:8]} — marking stale")
            stale.append(q)

    # Clean up stale queues
    if stale:
        async with _lock:
            active = _connections.get(user_id, [])
            _connections[user_id] = [q for q in active if q not in stale]

    return sent


def connected_user_ids() -> List[str]:
    """Return the list of user_ids with at least one active SSE connection."""
    return list(_connections.keys())
