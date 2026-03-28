"""
Notifications API — superadmin-only panel event feed.

GET    /api/notifications                — list (most recent first, 200 max)
GET    /api/notifications/unread-count   — {count: N}
POST   /api/notifications/{id}/read      — mark single read
POST   /api/notifications/read-all       — mark all read
DELETE /api/notifications/{id}           — delete single
DELETE /api/notifications                — clear all
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func

from app.auth import require_admin
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _fmt(n: Notification) -> dict:
    try:
        details = json.loads(n.details or "{}")
    except Exception:
        details = {}
    return {
        "id":         n.id,
        "type":       n.type,
        "title":      n.title,
        "message":    n.message,
        "details":    details,
        "is_read":    n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/unread-count")
async def unread_count(
    db:   AsyncSession = Depends(get_db),
    _user: User        = Depends(require_admin),
):
    result = await db.execute(
        select(func.count()).select_from(Notification).where(Notification.is_read == False)  # noqa: E712
    )
    return {"count": result.scalar_one()}


@router.get("")
async def list_notifications(
    db:   AsyncSession = Depends(get_db),
    _user: User        = Depends(require_admin),
):
    result = await db.execute(
        select(Notification)
        .order_by(Notification.created_at.desc())
        .limit(200)
    )
    return [_fmt(n) for n in result.scalars().all()]


@router.post("/{notif_id}/read")
async def mark_read(
    notif_id: int,
    db:       AsyncSession = Depends(get_db),
    _user:    User         = Depends(require_admin),
):
    await db.execute(
        update(Notification).where(Notification.id == notif_id).values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(
    db:    AsyncSession = Depends(get_db),
    _user: User         = Depends(require_admin),
):
    await db.execute(update(Notification).values(is_read=True))
    await db.commit()
    return {"ok": True}


@router.delete("/{notif_id}", status_code=204)
async def delete_notification(
    notif_id: int,
    db:       AsyncSession = Depends(get_db),
    _user:    User         = Depends(require_admin),
):
    n = await db.get(Notification, notif_id)
    if not n:
        raise HTTPException(404, "Notification not found")
    await db.delete(n)
    await db.commit()


@router.delete("", status_code=204)
async def clear_all(
    db:    AsyncSession = Depends(get_db),
    _user: User         = Depends(require_admin),
):
    await db.execute(delete(Notification))
    await db.commit()
