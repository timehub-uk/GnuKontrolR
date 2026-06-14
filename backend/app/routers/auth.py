"""Authentication endpoints."""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
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
    get_current_user, get_current_user_from_cookie_or_header,
    validate_password_strength, oauth2_scheme,
    set_tokens_in_cookies, clear_auth_cookies,
    get_token_from_cookie,
    SECRET_KEY, ALGORITHM, REFRESH_COOKIE,
)
from app.cache import get_redis
from jose import JWTError, jwt
import pyotp

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BLOCK_TTL            = 900  # 15 minutes in seconds
_MAX_FAILS            = 5
_REFRESH_IDLE_TIMEOUT = int(os.environ.get("REFRESH_IDLE_TIMEOUT_SECONDS", "86400"))  # 24h default idle timeout


def _get_client_ip(request: Request) -> str:
    """Return the client IP from X-Forwarded-For (trusting proxy chain) or direct connection.
    Prefers X-Forwarded-For when behind Traefik, falls back to direct connection."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # Take the leftmost IP (client's original IP)
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
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
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Step 1: Username/password login. Returns tokens or MFA challenge."""
    client_ip = _get_client_ip(request)

    # Check if IP or username is currently blocked
    r = await get_redis()
    if r is not None:
        try:
            blocked_ip = await r.get(f"auth:blocked:{client_ip}")
            blocked_user = await r.get(f"auth:user:blocked:{form_data.username}")
            if blocked_ip or blocked_user:
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
        r = await get_redis()
        if r is not None:
            try:
                # M15: Per-IP rate limiting (existing)
                fail_key = f"auth:fails:{client_ip}"
                count = await r.incr(fail_key)
                await r.expire(fail_key, _BLOCK_TTL)
                if count >= _MAX_FAILS:
                    await r.setex(f"auth:blocked:{client_ip}", _BLOCK_TTL, 1)

                # M15: Per-username rate limiting (prevents distributed brute-force)
                user_fail_key = f"auth:user:fails:{form_data.username}"
                user_count = await r.incr(user_fail_key)
                await r.expire(user_fail_key, _BLOCK_TTL)
                if user_count >= _MAX_FAILS:
                    await r.setex(f"auth:user:blocked:{form_data.username}", _BLOCK_TTL, 1)
            except Exception:
                pass
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="Account suspended")

    # Clear failure counters on success (M15: both IP and username)
    r = await get_redis()
    if r is not None:
        try:
            await r.delete(
                f"auth:fails:{client_ip}",
                f"auth:blocked:{client_ip}",
                f"auth:user:fails:{form_data.username}",
                f"auth:user:blocked:{form_data.username}",
            )
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

    # Set httpOnly cookies for XSS-safe session persistence
    access_token  = create_access_token(user.id, user.role, mfa_verified=False)
    refresh_token = create_refresh_token(user.id)
    token_resp = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user.role,
        username=user.username,
    )
    set_tokens_in_cookies(response, access_token, refresh_token)
    return token_resp


@router.post("/mfa-verify")
async def mfa_verify(
    body: MFALoginRequest,
    response: Response,
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
            digest=device.algorithm,
            digits=device.digits,
            interval=device.period,
        )
        if totp.verify(body.code, valid_window=1):
            device.last_used = datetime.now(timezone.utc)
            verified = True
            break

    if not verified:
        raise HTTPException(400, "Invalid MFA code")

    await db.commit()

    # Get user for token
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(401, "User not found")

    # Set httpOnly cookies
    access_token  = create_access_token(user.id, user.role, mfa_verified=True)
    refresh_token = create_refresh_token(user.id)
    token_resp = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user.role,
        username=user.username,
    )
    set_tokens_in_cookies(response, access_token, refresh_token)
    return token_resp


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
    current.password_changed_at = datetime.now(timezone.utc)

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

    from app.routers.setup import _apply_password_rotation_task

    # Run database ALTERs in background
    asyncio.create_task(_apply_password_rotation_task(req.new_password))

    # Recreate all site containers
    from app.models.domain import Domain
    from app.routers.domains import _create_container_for_domain
    from app.docker_client import stop_container, remove_container

    result_domains = await db.execute(select(Domain))
    domains = result_domains.scalars().all()

    for domain in domains:
        name = f"site_{domain.name.replace('.', '_').replace('-', '_')}"
        try:
            await stop_container(name)
        except Exception:
            pass
        try:
            await remove_container(name, force=True)
        except Exception:
            pass

        asyncio.create_task(_create_container_for_domain(domain.name, domain.php_version or "8.2", db, owner_email=domain.acme_email))

    await db.commit()

    return {"ok": True, "message": "Password changed successfully."}


@router.get("/session")
async def get_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Restore a session from the httpOnly refresh cookie (page reload).

    If a valid refresh_token cookie exists, returns a new access_token and user info.
    The frontend stores the access_token in memory and sends it as Bearer header.
    """
    from app.auth import ACCESS_COOKIE
    # Try access token cookie first (faster, no DB hit)
    access_cookie = get_token_from_cookie(request, ACCESS_COOKIE)
    if access_cookie:
        try:
            payload = jwt.decode(access_cookie, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") == "access":
                user_id = int(payload["sub"])
                user = await db.get(User, user_id)
                if user and user.is_active and not user.is_suspended:
                    return {
                        "access_token": access_cookie,
                        "token_type": "bearer",
                        "role": user.role,
                        "username": user.username,
                        "id": user.id,
                        "email": user.email,
                    }
        except (JWTError, KeyError, ValueError):
            pass  # Fall through to refresh token

    # Fall back to refresh token cookie
    refresh_cookie = get_token_from_cookie(request, REFRESH_COOKIE)
    if refresh_cookie:
        try:
            payload = jwt.decode(refresh_cookie, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") == "refresh":
                user_id = int(payload["sub"])
                user = await db.get(User, user_id)
                if user and user.is_active and not user.is_suspended:
                    access_token = create_access_token(user.id, user.role)
                    refresh_token = create_refresh_token(user.id)
                    response = JSONResponse({
                        "access_token": access_token,
                        "token_type": "bearer",
                        "role": user.role,
                        "username": user.username,
                        "id": user.id,
                        "email": user.email,
                    })
                    # Rotate refresh token and set new cookies
                    set_tokens_in_cookies(response, access_token, refresh_token)
                    # Blacklist old refresh token
                    r = await get_redis()
                    if r:
                        try:
                            await r.setex(f"token:blacklisted:{refresh_cookie}", 86400, 1)
                        except Exception:
                            pass
                    return response
        except (JWTError, KeyError, ValueError):
            pass

    # No valid session
    response = JSONResponse({"detail": "No active session"}, status_code=401)
    clear_auth_cookies(response)
    return response


@router.post("/refresh")
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a refresh token (from httpOnly cookie) for new tokens."""
    refresh_cookie = get_token_from_cookie(request, REFRESH_COOKIE)
    if not refresh_cookie:
        raise HTTPException(401, "No refresh token")

    # Check blacklist
    r = await get_redis()
    if r:
        try:
            blocked = await r.get(f"token:blacklisted:{refresh_cookie}")
            if blocked:
                raise HTTPException(401, "Token revoked")
        except HTTPException:
            raise
        except Exception:
            pass

    try:
        payload = jwt.decode(refresh_cookie, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(401, "Invalid token type")
        # M10: Check refresh token idle timeout — reject if token hasn't been
        # rotated within the idle window (even if not yet expired).
        iat = payload.get("iat")
        if iat is not None:
            elapsed = datetime.now(timezone.utc).timestamp() - iat
            if elapsed > _REFRESH_IDLE_TIMEOUT:
                raise HTTPException(401, "Session expired due to inactivity. Please log in again.")
        user_id = int(payload["sub"])
    except HTTPException:
        raise
    except (JWTError, ValueError):
        raise HTTPException(401, "Invalid or expired refresh token")

    user = await db.get(User, user_id)
    if not user or not user.is_active or user.is_suspended:
        raise HTTPException(401, "User not found or inactive")

    # Issue new tokens
    access_token  = create_access_token(user.id, user.role)
    new_refresh   = create_refresh_token(user.id)

    # Blacklist old refresh token
    if r:
        try:
            await r.setex(f"token:blacklisted:{refresh_cookie}", 86400, 1)
        except Exception:
            pass

    response = JSONResponse({
        "access_token": access_token,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
    })
    set_tokens_in_cookies(response, access_token, new_refresh)
    return response


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    current: User = Depends(get_current_user_from_cookie_or_header),
    token: str = "",
):
    """Logout the user and invalidate the JWT token via Redis blocklist.
    Clears httpOnly cookies so the session cannot be restored."""
    # Get token from Authorization header or cookie
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = get_token_from_cookie(request, ACCESS_COOKIE) or ""

    if token:
        r = await get_redis()
        if r is not None:
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                exp = payload.get("exp", 0)
                now = datetime.now(timezone.utc).timestamp()
                ttl = int(exp - now) if exp > now else 3600
                await r.setex(f"token:blacklisted:{token}", ttl, 1)
            except Exception as e:
                import logging
                logging.getLogger("webpanel.auth").warning("Failed to blacklist token: %s", e)

    # Clear auth cookies
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response
