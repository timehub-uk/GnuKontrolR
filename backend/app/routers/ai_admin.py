"""AI admin endpoints — session management, abuse log, global settings."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.auth import require_admin, get_current_user
from app.cache import get_redis
from app.database import get_db
from app.models.user import User, Role

router = APIRouter(prefix="/api/ai/admin", tags=["ai-admin"])

_AI_TOKEN_PREFIX = "ai:token"
_ABUSE_KEY_PREFIX = "ai:abuse"
_AI_CONFIG_KEY = "ai:config:enabled"


# ── Session management ─────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(_: User = Depends(require_admin)):
    """List all active AI sessions from Redis."""
    r = await get_redis()
    if not r:
        return []
    keys = [key async for key in r.scan_iter(match=f"{_AI_TOKEN_PREFIX}:*", count=100)]
    sessions = []
    for key in keys:
        # key format: ai:token:{owner_id}:{domain}:{agent}
        parts = key.split(":", 4)
        if len(parts) >= 5:
            ttl = await r.ttl(key)
            sessions.append({
                "owner_id": parts[2],
                "domain":   parts[3],
                "agent":    parts[4],
                "ttl_secs": ttl,
            })
    return sessions


@router.delete("/sessions/{owner_id}/{domain}/{agent}", status_code=204)
async def terminate_session(
    owner_id: str,
    domain: str,
    agent: str,
    _: User = Depends(require_admin),
):
    """Force-terminate an AI session."""
    r = await get_redis()
    if r:
        key = f"{_AI_TOKEN_PREFIX}:{owner_id}:{domain}:{agent}"
        await r.delete(key)


# ── Abuse log ─────────────────────────────────────────────────────────────────

@router.get("/abuse")
async def list_abuse_blocks(_: User = Depends(require_admin)):
    """List currently blocked users (abuse cooldown)."""
    r = await get_redis()
    if not r:
        return []
    keys = [key async for key in r.scan_iter(match=f"{_ABUSE_KEY_PREFIX}:*", count=100)]
    blocks = []
    for key in keys:
        parts = key.split(":")
        if len(parts) >= 3:
            ttl = await r.ttl(key)
            blocks.append({"owner_id": parts[2], "ttl_secs": ttl})
    return blocks


class BlockRequest(BaseModel):
    ttl_secs: Optional[int] = None


@router.post("/block/{user_id}", status_code=201)
async def manual_block(
    user_id: str,
    body: BlockRequest = None,
    _: User = Depends(require_admin),
):
    """Manually block a user from using AI."""
    r = await get_redis()
    if not r:
        raise HTTPException(503, "Redis unavailable")
    key = f"{_ABUSE_KEY_PREFIX}:{user_id}"
    if body and body.ttl_secs:
        await r.setex(key, body.ttl_secs, "1")
    else:
        await r.set(key, "1")  # permanent
    return {"ok": True, "blocked": user_id, "ttl_secs": body.ttl_secs if body else None}


@router.delete("/block/{user_id}", status_code=204)
async def manual_unblock(
    user_id: str,
    _: User = Depends(require_admin),
):
    """Remove a manual or abuse-triggered block."""
    r = await get_redis()
    if r:
        await r.delete(f"{_ABUSE_KEY_PREFIX}:{user_id}")


# ── User key wipe ──────────────────────────────────────────────────────────────

@router.delete("/users/{user_id}/keys", status_code=204)
async def wipe_user_keys(
    user_id: int,
    _: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Delete all AI provider credentials for a user."""
    from sqlalchemy import delete as sql_delete
    from app.models.ai_provider import AiProvider
    await db.execute(sql_delete(AiProvider).where(AiProvider.user_id == user_id))
    await db.commit()


# ── Global settings ────────────────────────────────────────────────────────────

class AiSettings(BaseModel):
    enabled: Optional[bool] = None


@router.get("/settings")
async def get_settings(_: User = Depends(require_admin)):
    """Get global AI settings."""
    r = await get_redis()
    enabled = True
    if r:
        val = await r.get(_AI_CONFIG_KEY)
        enabled = val != "0"
    return {"enabled": enabled}


@router.patch("/settings")
async def update_settings(
    body: AiSettings,
    _: User = Depends(require_admin),
):
    """Update global AI settings."""
    r = await get_redis()
    if not r:
        raise HTTPException(503, "Redis unavailable")
    if body.enabled is not None:
        await r.set(_AI_CONFIG_KEY, "1" if body.enabled else "0")
    return {"ok": True}
