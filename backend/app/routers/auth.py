"""Authentication endpoints."""
import ipaddress
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.notify import push as notify_push
from app.models.user import User, Role
from app.models.mfa_device import MFADevice
from app.models.password_policy import PasswordHistory
from app.auth import (
    verify_password, hash_password,
    create_access_token, create_refresh_token, create_mfa_token,
    get_current_user, validate_password_strength,
)
from app.cache import get_redis
import pyotp

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


class MFARequiredResponse(BaseModel):
    mfa_required: bool = True
    mfa_token: str
    devices: list[dict]


class MFALoginRequest(BaseModel):
    mfa_token: str
    code: str


@router.post("/token")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Step 1: Username/password login. Returns tokens or MFA challenge."""
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
                pass

    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    auth_ok = user is not None and verify_password(form_data.password, user.hashed_password)

    if not auth_ok:
        if not is_private:
            r = await get_redis()
            if r is not None:
                try:
                    fail_key = f"auth:fails:{client_ip}"
                    count = await r.incr(fail_key)
                    await r.expire(fail_key, _BLOCK_TTL)
                    if count >= _MAX_FAILS:
                        await r.setex(f"auth:blocked:{client_ip}", _BLOCK_TTL, 1)
                except Exception:
                    pass
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="Account suspended")

    # Clear failure counter on success
    if not is_private:
        r = await get_redis()
        if r is not None:
            try:
                await r.delete(f"auth:fails:{client_ip}", f"auth:blocked:{client_ip}")
            except Exception:
                pass

    # Check for active MFA devices
    mfa_result = await db.execute(
        select(MFADevice).where(
            MFADevice.user_id == user.id,
            MFADevice.is_active == True,
        )
    )
    mfa_devices = mfa_result.scalars().all()

    if mfa_devices:
        # Return MFA challenge token instead of access token
        mfa_token = create_mfa_token(user.id)
        return {
            "mfa_required": True,
            "mfa_token": mfa_token,
            "devices": [
                {"id": d.id, "name": d.name, "type": "totp"}
                for d in mfa_devices
            ],
        }

    return TokenResponse(
        access_token=create_access_token(user.id, user.role, mfa_verified=False),
        refresh_token=create_refresh_token(user.id),
        role=user.role,
        username=user.username,
    )


@router.post("/mfa-verify")
async def mfa_verify(
    body: MFALoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Step 2: Verify MFA code with temporary token to complete login."""
    from app.auth import SECRET_KEY, ALGORITHM
    from jose import jwt as _jwt

    # Decode the MFA token
    try:
        payload = _jwt.decode(body.mfa_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "mfa_challenge":
            raise HTTPException(401, "Invalid MFA token")
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(401, "Invalid or expired MFA token")

    # Verify the TOTP code against any active device
    result = await db.execute(
        select(MFADevice).where(
            MFADevice.user_id == user_id,
            MFADevice.is_active == True,
        )
    )
    devices = result.scalars().all()

    if not devices:
        raise HTTPException(400, "No active MFA devices found")

    verified = False
    for device in devices:
        totp = pyotp.TOTP(
            device.secret,
            algorithm=device.algorithm,
            digits=device.digits,
            interval=device.period,
        )
        if totp.verify(body.code, valid_window=1):
            device.last_used = datetime.utcnow()
            verified = True
            break

    if not verified:
        raise HTTPException(400, "Invalid MFA code")

    await db.commit()

    # Get user for token
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")

    return TokenResponse(
        access_token=create_access_token(user.id, user.role, mfa_verified=True),
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
                await r.expire(reg_key, 3600)
            if count > 5:
                raise HTTPException(429, "Too many registration attempts. Try again in 1 hour.")

    # Validate password strength
    pw_error = validate_password_strength(req.password)
    if pw_error:
        raise HTTPException(400, pw_error)

    # First user becomes superadmin
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
                "Name":     user.full_name or "\u2014",
            },
        ))

    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/me")
async def me(current: User = Depends(get_current_user)):
    return {
        "id":             current.id,
        "username":       current.username,
        "email":          current.email,
        "full_name":      current.full_name,
        "preferred_name": current.preferred_name or "",
        "role":           current.role,
        "is_active":      current.is_active,
        "disk_quota_mb":  current.disk_quota_mb,
        "bw_quota_mb":    current.bw_quota_mb,
        "max_domains":    current.max_domains,
        "company":        current.company,
        "phone":          current.phone,
        "address_line1":  current.address_line1,
        "address_line2":  current.address_line2,
        "city":           current.city,
        "state":          current.state,
        "postcode":       current.postcode,
        "country":        current.country,
        "mfa_enabled":    current.mfa_enabled,
        "password_changed_at": current.password_changed_at.isoformat() if current.password_changed_at else None,
        "consent_version": current.consent_version,
        "marketing_opt_in": current.marketing_opt_in,
    }


# ── Pydantic models ──────────────────────────────────────────────────────────
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the authenticated user's password with history check."""
    # 1. Verify current password
    if not verify_password(req.current_password, current.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    # 2. Validate new password strength
    strength_errors = validate_password_strength(req.new_password)
    if strength_errors:
        raise HTTPException(status_code=400, detail="; ".join(strength_errors))

    # 3. Check password history (prevent reuse of last N passwords)
    history_result = await db.execute(
        select(PasswordHistory)
        .where(PasswordHistory.user_id == current.id)
        .order_by(PasswordHistory.created_at.desc())
    )
    recent = history_result.scalars().all()
    for entry in recent:
        if verify_password(req.new_password, entry.hashed_password):
            raise HTTPException(
                status_code=400,
                detail="You have used this password recently. Please choose a different password.",
            )

    # 4. Hash new password
    new_hash = hash_password(req.new_password)
    old_hash = current.hashed_password
    current.hashed_password = new_hash
    current.password_changed_at = datetime.utcnow()

    # 5. Archive old password to history (keep last N)
    # Use PASSWORD_HISTORY from env or default to 5
    max_history = int(os.environ.get("PASSWORD_HISTORY", "5"))
    history = PasswordHistory(user_id=current.id, hashed_password=old_hash)
    db.add(history)

    # Prune excess history entries
    if len(recent) >= max_history:
        # Keep the N-1 most recent, plus the one we just added
        to_keep = recent[-(max_history - 1):] if max_history > 1 else []
        keep_ids = [h.id for h in to_keep]
        from sqlalchemy import delete as _delete
        await db.execute(
            _delete(PasswordHistory)
            .where(
                PasswordHistory.user_id == current.id,
                PasswordHistory.id.notin_(keep_ids) if keep_ids else True,
            )
        )

    await db.commit()

    return {"ok": True, "message": "Password changed successfully."}
