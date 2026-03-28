"""Authentication endpoints."""
import ipaddress
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.notify import push as notify_push
from app.models.user import User, Role
from app.auth import (
    verify_password, hash_password,
    create_access_token, create_refresh_token,
    get_current_user,
)
from app.cache import get_redis

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BLOCK_TTL = 900  # 15 minutes in seconds
_MAX_FAILS = 5


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def _get_client_ip(request: Request) -> str:
    """Return the direct connection IP. X-Forwarded-For is intentionally ignored
    because port 8000 is publicly reachable and the header is trivially spoofable."""
    return request.client.host if request.client else "unknown"


class RegisterRequest(BaseModel):
    # Account
    username:  str
    email:     EmailStr
    password:  str
    full_name: str = ""

    # Customer profile
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


@router.post("/token", response_model=TokenResponse)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    client_ip = _get_client_ip(request)
    is_private = _is_private_ip(client_ip) or client_ip == "unknown"

    # Check if IP is currently blocked (public IPs only)
    if not is_private:
        r = await get_redis()
        if r is not None:
            try:
                blocked = await r.get(f"auth:blocked:{client_ip}")
                if blocked:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Too many failed attempts. Try again in 15 minutes.",
                    )
            except HTTPException:
                raise
            except Exception:
                pass  # Redis unavailable — allow login to proceed

    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    auth_ok = user is not None and verify_password(form.password, user.hashed_password)

    if not auth_ok:
        # Increment failure counter for public IPs
        if not is_private:
            r = await get_redis()
            if r is not None:
                try:
                    fail_key = f"auth:fails:{client_ip}"
                    count = await r.incr(fail_key)
                    await r.expire(fail_key, _BLOCK_TTL)  # Always refresh TTL so window slides
                    if count >= _MAX_FAILS:
                        await r.setex(f"auth:blocked:{client_ip}", _BLOCK_TTL, 1)
                except Exception:
                    pass  # Redis unavailable — skip rate limiting
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="Account suspended")

    # Successful login — clear failure counter for public IPs
    if not is_private:
        r = await get_redis()
        if r is not None:
            try:
                await r.delete(f"auth:fails:{client_ip}", f"auth:blocked:{client_ip}")
            except Exception:
                pass

    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        role=user.role,
        username=user.username,
    )


@router.post("/register", status_code=201)
async def register(req: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # IP-based rate limiting (5 attempts per hour)
    client_ip = request.client.host if request.client else "unknown"
    if client_ip != "unknown":
        r = await get_redis()
        if r:
            reg_key = f"auth:register:{client_ip}"
            count = await r.incr(reg_key)
            if count == 1:
                await r.expire(reg_key, 3600)  # 1 hour window
            if count > 5:
                raise HTTPException(429, "Too many registration attempts. Try again in 1 hour.")

    # First user becomes superadmin
    result = await db.execute(select(User))
    is_first = result.first() is None
    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role=Role.superadmin if is_first else Role.user,
        # Profile fields
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
    if not is_first:
        import asyncio as _asyncio
        _asyncio.create_task(notify_push(
            db,
            type    = "user_registered",
            title   = f"New user registered: {user.username}",
            message = f"'{user.username}' ({user.email}) registered a new account.",
            details = {
                "Username": user.username,
                "Email":    user.email,
                "Role":     user.role,
                "Name":     user.full_name or "—",
            },
        ))
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
        # Profile
        "company":       current.company,
        "phone":         current.phone,
        "address_line1": current.address_line1,
        "address_line2": current.address_line2,
        "city":          current.city,
        "state":         current.state,
        "postcode":      current.postcode,
        "country":       current.country,
    }
