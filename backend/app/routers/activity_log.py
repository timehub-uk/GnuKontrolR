"""
Per-user private activity log.

Every authenticated API request is appended to the requesting user's log.
Users can only read their own log. Admins can read any user's log.
Entries are stored in the database (RequestLog model) and include:
  - UUID event ID
  - timestamp
  - method + path
  - HTTP status
  - duration (ms)
  - IP address (hashed for privacy)
"""
import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete

from app.auth import get_current_user, get_current_user_query, require_admin
from app.database import get_db
from app.models.request_log import RequestLog
from app.models.user import User

router = APIRouter(prefix="/api/log", tags=["activity-log"])

LOG_RETENTION = 1000   # keep last N entries per user


async def record_request(
    db,
    user_id: int,
    event_id: str,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    ip_hash: str,
):
    """Append one entry and prune to LOG_RETENTION rows for this user."""
    entry = RequestLog(
        user_id     = user_id,
        event_id    = event_id,
        method      = method,
        path        = path,
        status      = status,
        duration_ms = round(duration_ms, 1),
        ip_hash     = ip_hash,
        created_at  = datetime.utcnow(),
    )
    db.add(entry)
    await db.commit()
    # Push to any connected SSE clients for this user
    _sse_broadcast(user_id, {
        "event_id": event_id, "method": method, "path": path,
        "status": status, "duration_ms": round(duration_ms, 1),
        "timestamp": entry.created_at.isoformat(),
    })

    # Prune: keep only the most recent LOG_RETENTION entries for this user
    subq = (
        select(RequestLog.id)
        .where(RequestLog.user_id == user_id)
        .order_by(RequestLog.created_at.desc())
        .limit(LOG_RETENTION)
        .subquery()
    )
    await db.execute(
        delete(RequestLog).where(
            RequestLog.user_id == user_id,
            RequestLog.id.not_in(select(subq.c.id)),
        )
    )
    await db.commit()


@router.get("/me")
async def get_my_log(
    limit: int = 200,
    offset: int = 0,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the calling user's own request log, newest first."""
    result = await db.execute(
        select(RequestLog)
        .where(RequestLog.user_id == user.id)
        .order_by(RequestLog.created_at.desc())
        .limit(min(limit, 500))
        .offset(offset)
    )
    entries = result.scalars().all()
    return {
        "user_id": user.id,
        "entries": [_serialize(e) for e in entries],
        "total":   len(entries),
    }


@router.get("/user/{user_id}")
async def get_user_log(
    user_id: int,
    limit: int = 200,
    offset: int = 0,
    db=Depends(get_db),
    _=Depends(require_admin),
):
    """Admin: read any user's log."""
    result = await db.execute(
        select(RequestLog)
        .where(RequestLog.user_id == user_id)
        .order_by(RequestLog.created_at.desc())
        .limit(min(limit, 500))
        .offset(offset)
    )
    entries = result.scalars().all()
    return {
        "user_id": user_id,
        "entries": [_serialize(e) for e in entries],
        "total":   len(entries),
    }


@router.delete("/me")
async def clear_my_log(db=Depends(get_db), user: User = Depends(get_current_user)):
    """User clears their own log."""
    await db.execute(delete(RequestLog).where(RequestLog.user_id == user.id))
    await db.commit()
    return {"ok": True}


def _serialize(entry: RequestLog) -> dict:
    return {
        "event_id":    entry.event_id,
        "method":      entry.method,
        "path":        entry.path,
        "status":      entry.status,
        "duration_ms": entry.duration_ms,
        "ip_hash":     entry.ip_hash,
        "timestamp":   entry.created_at.isoformat(),
    }


# ── In-memory SSE broadcast bus ───────────────────────────────────────────────
# Each connected SSE client is represented by an asyncio.Queue.
_SSE_CLIENTS: dict[int, list[asyncio.Queue]] = {}   # user_id → list of queues


def _sse_broadcast(user_id: int, event: dict) -> None:
    """Push *event* to all SSE clients subscribed for *user_id*."""
    for q in _SSE_CLIENTS.get(user_id, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def _sse_generator(user_id: int, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted lines, keeping the connection alive with pings."""
    yield "retry: 3000\n\n"   # tell the browser to retry after 3 s on disconnect
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield ": ping\n\n"   # keep-alive comment line
    except asyncio.CancelledError:
        pass
    finally:
        queues = _SSE_CLIENTS.get(user_id, [])
        if queue in queues:
            queues.remove(queue)


@router.get("/stream")
async def stream_activity(user: User = Depends(get_current_user_query)):
    """SSE endpoint — streams new activity log events to the browser in real time."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _SSE_CLIENTS.setdefault(user.id, []).append(queue)
    return StreamingResponse(
        _sse_generator(user.id, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
        },
    )
