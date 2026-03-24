"""Authentication endpoints with brute-force protection."""
import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token, create_refresh_token,
    get_current_user, hash_password, verify_password,
)
from app.database import get_db
from app.models.user import Role, User

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("auth")

# ── Brute-force tracking (in-process; survives across requests but not restarts)
# For production at scale use Redis; this covers single-instance deployments.
# Structure: { key -> {"attempts": int, "locked_until": float, "permanent": bool} }
_ATTEMPTS: dict = defaultdict(lambda: {"attempts": 0, "locked_until": 0.0, "permanent": False})
_LOCK = asyncio.Lock()

# Lockout schedule: attempts → cooldown minutes
# 1-4:   no lockout
# 5:     5 min
# 6:     30 min
# 7:     120 min
# 8:     250 min
# 9:     1000 min
# 10+:   permanent block (firewall entry logged)
_COOLDOWNS = {5: 5, 6: 30, 7: 120, 8: 250, 9: 1000}


def _cooldown_minutes(attempts: int) -> Optional[int]:
    """Return lockout duration in minutes for this attempt count, or None if none."""
    return _COOLDOWNS.get(attempts)


async def _check_and_record_failure(key: str) -> None:
    """Record a failed attempt and raise 429 if locked out."""
    async with _LOCK:
        entry = _ATTEMPTS[key]

        # Already permanently blocked
        if entry["permanent"]:
            log.warning("BRUTE_FORCE_PERMANENT_BLOCK key=%s", key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Your access has been permanently blocked due to repeated failed logins. Contact an administrator.",
            )

        # Check active cooldown
        if entry["locked_until"] > time.time():
            remaining = int((entry["locked_until"] - time.time()) / 60) + 1
            log.warning("BRUTE_FORCE_LOCKED key=%s remaining_min=%d", key, remaining)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts. Try again in {remaining} minute(s).",
            )

        # Record this failure
        entry["attempts"] += 1
        n = entry["attempts"]
        log.warning("BRUTE_FORCE_FAIL key=%s attempt=%d", key, n)

        if n >= 10:
            entry["permanent"] = True
            log.critical(
                "BRUTE_FORCE_PERMANENT key=%s — 10+ consecutive failures. "
                "Recommend adding this IP to firewall (iptables -I INPUT -s %s -j DROP).",
                key, key.split(":")[0],
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Your access has been permanently blocked due to repeated failed logins. Contact an administrator.",
            )

        minutes = _cooldown_minutes(n)
        if minutes:
            entry["locked_until"] = time.time() + minutes * 60
            log.warning("BRUTE_FORCE_LOCKOUT key=%s duration_min=%d", key, minutes)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed attempts ({n}). Locked out for {minutes} minute(s).",
            )


async def _clear_failures(key: str) -> None:
    """Reset failure count on successful login."""
    async with _LOCK:
        _ATTEMPTS.pop(key, None)


# ── Models ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username:      str
    email:         EmailStr
    password:      str
    full_name:     str = ""
    company:       str = ""
    phone:         str = ""
    address_line1: str = ""
    address_line2: str = ""
    city:          str = ""
    state:         str = ""
    postcode:      str = ""
    country:       str = ""
    vat_number:    str = ""


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    role:          str
    username:      str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    # Composite key: IP + username to limit per-account and per-IP attacks
    client_ip = request.client.host if request.client else "unknown"
    key_ip   = f"{client_ip}:*"           # per-IP attempts
    key_user = f"{client_ip}:{form.username}"  # per-IP+username

    # Check lockout BEFORE hitting the DB (saves compute on DoS)
    for key in (key_ip, key_user):
        async with _LOCK:
            entry = _ATTEMPTS[key]
            if entry.get("permanent"):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Your access has been permanently blocked. Contact an administrator.",
                )
            if entry.get("locked_until", 0) > time.time():
                remaining = int((entry["locked_until"] - time.time()) / 60) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed login attempts. Try again in {remaining} minute(s).",
                )

    # Authenticate
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        # Record failure under both keys
        for key in (key_ip, key_user):
            try:
                await _check_and_record_failure(key)
            except HTTPException:
                pass  # continue to second key
        # Re-raise after recording both
        for key in (key_ip, key_user):
            async with _LOCK:
                entry = _ATTEMPTS[key]
                if entry.get("permanent") or entry.get("locked_until", 0) > time.time():
                    n = entry["attempts"]
                    if entry.get("permanent"):
                        raise HTTPException(
                            status_code=429,
                            detail="Your access has been permanently blocked. Contact an administrator.",
                        )
                    remaining = int((entry["locked_until"] - time.time()) / 60) + 1
                    raise HTTPException(
                        status_code=429,
                        detail=f"Too many failed attempts ({n}). Locked out for {remaining} minute(s).",
                    )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="Account suspended")

    # Success — clear any failure counters
    await _clear_failures(key_ip)
    await _clear_failures(key_user)
    log.info("LOGIN_OK user=%s ip=%s", user.username, client_ip)

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        role=user.role,
        username=user.username,
    )


@router.post("/register", status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    is_first = result.first() is None
    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=Role.superadmin if is_first else Role.user,
        company=req.company,
        phone=req.phone,
        address_line1=req.address_line1,
        address_line2=req.address_line2,
        city=req.city,
        state=req.state,
        postcode=req.postcode,
        country=req.country,
        vat_number=req.vat_number,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/me")
async def me(current: User = Depends(get_current_user)):
    return {
        "id":            current.id,
        "username":      current.username,
        "email":         current.email,
        "full_name":     current.full_name,
        "role":          current.role,
        "is_active":     current.is_active,
        "disk_quota_mb": current.disk_quota_mb,
        "bw_quota_mb":   current.bw_quota_mb,
        "max_domains":   current.max_domains,
        "company":       current.company,
        "phone":         current.phone,
        "address_line1": current.address_line1,
        "address_line2": current.address_line2,
        "city":          current.city,
        "state":         current.state,
        "postcode":      current.postcode,
        "country":       current.country,
    }
