"""JWT authentication and password hashing."""
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User, Role
from app.cache import get_redis

_DEFAULT_KEY   = "change-me-in-production-use-32-char-secret"
SECRET_KEY     = os.environ.get("SECRET_KEY", _DEFAULT_KEY)
_IS_PRODUCTION = os.environ.get("ENVIRONMENT", "").lower() == "production"
import logging as _log
if SECRET_KEY == _DEFAULT_KEY:
    if _IS_PRODUCTION:
        _log.getLogger("webpanel").critical(
            "FATAL: SECRET_KEY is the default value in a production environment. "
            "Set a strong random SECRET_KEY before starting."
        )
        raise SystemExit("Refusing to start with default SECRET_KEY in production.")
    else:
        _log.getLogger("webpanel").warning(
            "SECURITY: SECRET_KEY is set to the default value. "
            "Set a strong random SECRET_KEY before deploying to production."
        )
ALGORITHM       = "HS256"
ACCESS_EXPIRE   = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 15))
REFRESH_EXPIRE  = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 7))
COOKIE_DOMAIN   = os.environ.get("PANEL_DOMAIN", None)
COOKIE_SECURE   = _IS_PRODUCTION
ACCESS_COOKIE   = "access_token"
REFRESH_COOKIE  = "refresh_token"

pwd_context    = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme  = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


# ── Password helpers ──────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def validate_password_strength(password: str) -> Optional[str]:
    """Validate password against security policy rules.
    Returns an error message if invalid, None if valid."""
    if len(password) < 12:
        return "Password must be at least 12 characters long"
    if not re.search(r'[A-Z]', password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return "Password must contain at least one digit"
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>/?\\|`~]', password):
        return "Password must contain at least one special character"
    return None


# ── Token helpers ─────────────────────────────────────────────────

def create_token(data: dict, expires_delta: timedelta) -> str:
    payload = {**data, "exp": datetime.now(timezone.utc) + expires_delta}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int, role: str, mfa_verified: bool = False) -> str:
    return create_token(
        {"sub": str(user_id), "role": role, "type": "access", "mfa": mfa_verified},
        timedelta(minutes=ACCESS_EXPIRE),
    )


def create_refresh_token(user_id: int) -> str:
    return create_token(
        {"sub": str(user_id), "type": "refresh"},
        timedelta(days=REFRESH_EXPIRE),
    )


def create_mfa_token(user_id: int) -> str:
    """Short-lived token for MFA verification step."""
    return create_token(
        {"sub": str(user_id), "type": "mfa_challenge"},
        timedelta(minutes=5),
    )


# ── Current user dependency ───────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Check Redis blacklist for logged-out tokens
    r = await get_redis()
    if r is not None:
        try:
            is_blocked = await r.get(f"token:blacklisted:{token}")
            if is_blocked:
                raise credentials_exc
        except HTTPException:
            raise
        except Exception:
            pass

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exc
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.is_suspended:
        raise credentials_exc
    return user


def require_role(*roles: Role):
    """Dependency factory: raise 403 if user lacks required role."""
    async def _check(current: User = Depends(get_current_user)) -> User:
        if current.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current
    return _check


require_superadmin = require_role(Role.superadmin)
require_admin      = require_role(Role.superadmin, Role.admin)
require_reseller   = require_role(Role.superadmin, Role.admin, Role.reseller)


async def get_current_user_query(
    token: str = "",
    db: AsyncSession = Depends(get_db),
) -> User:
    """Like get_current_user but reads token from the ?token= query param.
    Used for SSE and WebSocket endpoints where headers cannot be set."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exc
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.is_suspended:
        raise credentials_exc
    return user


def _decode_token(token: str) -> Optional[int]:
    """
    Lightweight token → user_id decode used by the request-logging middleware.
    Returns None on any error rather than raising — logging must never block a request.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        sub = payload.get("sub")
        return int(sub) if sub else None
    except Exception:
        return None


async def get_user_password(db: AsyncSession, user_id: int = 1) -> str:
    """Retrieve the stored encrypted password for a user.

    Returns an empty string if no user found or no password stored.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user and user.encrypted_password:
        return user.encrypted_password
    return ""


# ── httpOnly cookie helpers ─────────────────────────────────────────────

def set_tokens_in_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set httpOnly, SameSite=Strict cookies for access and refresh tokens.

    These cookies are invisible to JavaScript, preventing XSS-based token theft.
    The frontend uses the access_token from the Authorization header (set from
    the response body) while the httpOnly cookie serves as a secure fallback
    for page-load session recovery via GET /api/auth/session.
    """
    max_age_access  = ACCESS_EXPIRE * 60
    max_age_refresh = REFRESH_EXPIRE * 24 * 3600

    for name, token, max_age in (
        (ACCESS_COOKIE,  access_token,  max_age_access),
        (REFRESH_COOKIE, refresh_token, max_age_refresh),
    ):
        response.set_cookie(
            key=name,
            value=token,
            max_age=max_age,
            expires=max_age,
            path="/",
            domain=COOKIE_DOMAIN,
            secure=COOKIE_SECURE,
            httponly=True,
            samesite="strict",
        )


def clear_auth_cookies(response: Response) -> None:
    """Clear authentication cookies (logout)."""
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(
            key=name,
            path="/",
            domain=COOKIE_DOMAIN,
            secure=COOKIE_SECURE,
            httponly=True,
            samesite="strict",
        )


def get_token_from_cookie(request: Request, cookie_name: str = ACCESS_COOKIE) -> Optional[str]:
    """Extract a token from an httpOnly cookie (fallback if no Authorization header)."""
    return request.cookies.get(cookie_name)


async def get_current_user_from_cookie_or_header(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Like get_current_user but also checks the httpOnly cookie for the token.

    Priority: Authorization header > access_token cookie.
    This dual-source approach supports:
    - SPA: Bearer token in memory (from login response body), sent via Authorization header
    - Page reload: httpOnly access_token cookie set by login endpoint
    - SSE/WebSocket: token in query param
    """
    token = request.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        token = token[7:]
    elif "token" in request.query_params:
        token = request.query_params["token"]
    else:
        token = get_token_from_cookie(request, ACCESS_COOKIE) or ""

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exc

    # Check Redis blacklist
    r = await get_redis()
    if r is not None:
        try:
            is_blocked = await r.get(f"token:blacklisted:{token}")
            if is_blocked:
                raise credentials_exc
        except HTTPException:
            raise
        except Exception:
            pass

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise credentials_exc
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.is_suspended:
        raise credentials_exc
    return user
