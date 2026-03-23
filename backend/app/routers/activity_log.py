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
import hashlib
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete

from app.auth import get_current_user, require_admin
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
    db.add(RequestLog(
        user_id     = user_id,
        event_id    = event_id,
        method      = method,
        path        = path,
        status      = status,
        duration_ms = round(duration_ms, 1),
        ip_hash     = ip_hash,
        created_at  = datetime.utcnow(),
    ))
    await db.commit()

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
